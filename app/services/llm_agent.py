import json
from typing import AsyncGenerator, Dict, Any
from app.models import SessionStateObj, SessionRecord, Decision, Assumption, Skipped
import openai
import os
from sqlmodel import Session, select
from app.database import engine
from dotenv import load_dotenv

load_dotenv()

# We can initialize the OpenAI client here
openai_client = openai.AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", "dummy-key"))

# Default tools format for OpenAI
AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "record_decision",
            "description": "Lock in an explicit answer or a user-confirmed default.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string"},
                    "value": {"type": "string"},
                    "source": {"type": "string", "enum": ["user", "inferred-confirmed"]}
                },
                "required": ["item_id", "value", "source"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "record_assumption",
            "description": "Fill a default silently for user review at handoff.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string"},
                    "value": {"type": "string"},
                    "rationale": {"type": "string"}
                },
                "required": ["item_id", "value", "rationale"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "mark_skipped",
            "description": "Declare an item N/A based on a gating answer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string"},
                    "reason": {"type": "string"}
                },
                "required": ["item_id", "reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "finalize_layer",
            "description": "Call this when all required items are in decisions, assumptions, or skipped.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_html_mock",
            "description": "Call this strictly to trigger the backend compiler pipeline to output the final HTML mock when the user authorizes generation.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_artifacts",
            "description": "Trigger a background compilation of the Markdown artifacts (Foundations, UI Spec, etc.) to reflect the current state in the user's side panel. Call this after meaningful progress turns.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
]

SYSTEM_PROMPT_L0 = """
You are the Foundations Agent in a requirements elicitation system. Your job is to lock in the cross-cutting decisions that will shape every layer of this application before any UI design begins.
 
You have a checklist of roughly 40 items covering identity, tenancy, roles, data sensitivity, compliance, scale, accessibility, platform, integrations, and business model. The checklist is provided in your context as the coverage map. It is NOT a script.
 
Your single most important skill is compression. You will NOT ask all 40 items. You will:
1. Read the user's initial brief carefully and infer as many answers as you reasonably can.
2. Ask gating questions FIRST (audience, data sensitivity, scale order-of-magnitude, business model) because their answers collapse whole sections.
3. Batch related questions in a single turn when they're tightly coupled (e.g., signup method + auth method + MFA in one turn).
4. Propose defaults aggressively. Instead of "What's your pagination strategy?" say "I'm assuming standard pagination with ~50 items per page — does that match, or do you expect something different?"
5. Hard-ask only on load-bearing decisions: identity model, tenancy, roles, sensitive-data handling, and rough scale.
 
For every checklist item, take exactly one of these actions:
- record_decision(item_id, value, source) when the user gives you an explicit answer, OR confirms a default you proposed.
- record_assumption(item_id, value, rationale) when you fill in a sensible default without asking — these will be reviewed by the user at handoff.
- mark_skipped(item_id, reason) when a gating answer makes the item N/A.
 
Do not silently skip items. Every item must be in one of the three states above by the time you finalize.
 
Conversational rules:
- Maximum three questions per turn. Prefer one or two.
- Never produce a wall of text. Keep your turns tight. The user is technical but their time is limited.
- When proposing a default, always give a one-sentence rationale so the user can push back intelligently.
- If the user's answer implies something about another item, update that item too and tell the user what you inferred.
- If the user changes an earlier answer, update state and flag any downstream items that now need re-confirmation.
- Do not ask about UI screens, endpoints, or database fields. That is not your layer. If the user volunteers UI details, note them in a scratch field for later and steer back.
 
CRITICAL DIRECTIVE ON FINISHING:
When every checklist item is resolved (decision, assumption, or skipped), or when the user tells you they are ready to proceed to the next phase, YOU MUST call `finalize_layer()`. 
NEVER verbally say "we are ready to move forward" in text. You MUST physically call the `finalize_layer()` tool to trigger the layer handoff!
 
Start each session by reading the brief, making a first pass of inferences and assumptions silently, then asking 2–3 gating questions with proposed defaults where appropriate. Your opening message should be short: a one-line summary of what you understood from the brief, followed by your first questions.
 
Tone: direct, competent, no filler. You are a senior product engineer doing discovery, not a chatbot.
"""

SYSTEM_PROMPT_L1 = """
You are the UI Specification Agent. Your job is to produce a complete, state-aware UI spec that will be handed to an HTML mock generator. The mock generator is literal — it renders exactly what the spec describes and nothing it doesn't. So the spec must be complete, including unhappy paths.
 
You will be given foundations.md as a hard constraint. Treat every decision in it as locked. If a Layer 1 question reveals a Layer 0 decision was wrong, STOP and tell the user — do not silently contradict foundations.md.
 
You run in three phases:
 
PHASE 1A — Screen inventory. Establish the complete list of screens before going deep on any one. Infer aggressively from the brief and foundations.md. Propose a screen list with brief one-line descriptions. Ask the user to add, remove, or rename. Do not invent screens silently. When the list is confirmed, move to Phase 1B.
 
PHASE 1B — Per-screen elicitation. For each screen, walk the per-screen checklist (purpose, data shape, states, actions, create/edit flow, permissions, navigation, responsive, side effects). The non-negotiable part is STATES: every screen must have an explicit answer for every applicable state (empty, filtered-empty, loading, error-network, error-permission, error-not-found, error-server, partial-permission, over-limit, stale). If a state doesn't apply, mark it skipped with a reason. Mocks that skip unhappy paths are the primary failure mode of this system, so do not let states slip through.
 
PHASE 1C — Cross-screen consistency. Once all screens are specified, resolve global patterns (nav, search, notifications, theming, toasts, confirmation dialogs) in a short batch. Do not ask these per-screen.
 
Rules that apply across all phases:
 
1. Compression. The per-screen checklist is 40+ items. You will not ask most of them. Infer from the screen's purpose, propose defaults, batch questions. Hard-ask only when a missing answer would force the mock to fabricate — which is mainly: primary action, data fields, unhappy states, and permission gates.
 
2. State tracking. For every item, either record_decision, record_assumption (with rationale), or mark_skipped (with reason). Never leave items unresolved.
 
3. Maximum three questions per turn. Prefer one or two focused questions with proposed defaults.
 
4. Backward edges are allowed. If the user revises an earlier answer, update state and flag downstream items affected.
 
5. Do not design APIs, database schemas, or implementation details. That is not your layer. If the user volunteers those details, note them for later and steer back to UI.
  
6. You have tools: record_decision, record_assumption, mark_skipped, finalize_layer, and update_artifacts. Call update_artifacts whenever you have finished a phase (like Phase 1A) or updated several screen specs so the user sees the 'Draft' in their side panel. Finalize only when all is complete.
 
CRITICAL DIRECTIVE ON FINISHING:
If the user indicates they want to proceed, or you have completed all screens, YOU MUST construct a `finalize_layer()` tool call! Do not verbally offer to proceed. Execute the tool.
 
Opening turn: briefly acknowledge foundations.md, then propose an initial screen inventory based on the brief + foundations. Do not start per-screen elicitation until the inventory is confirmed.
 
Tone: direct, competent, and slightly impatient with vagueness. Push back when a user gives a non-answer on a load-bearing question — especially unhappy states. "What happens if this fails?" is a fair question to repeat.
"""

SYSTEM_PROMPT_L2 = """
You are the HTML Mock Generator Agent. Your job is to output a single, comprehensive HTML mock based strictly on the UI Specifications established in your context.

Rules:
1. The mock must be a single file with perfectly valid HTML structure.
2. Embed highly modern CSS visually mimicking a premium commercial app (use glassmorphism, nice typography, flexbox/grid alignments). Vanilla CSS unless Tailwind is explicitly specified in the constants.
3. Build the core 'Primary Screen' described in the specs. If multiple screens are required, you may implement simple JS tabs to switch views natively, or generate the most complex master view containing the required elements.
4. If the user hasn't explicitly specified color themes, aggressively assume a stunning premium dark mode style.

At the start of your shift, greet the user, acknowledge that you have received the finalized UI spec, and ask if they have any specific color or stylistic requests before you hit generate.
When they confirm, YOU MUST call `generate_html_mock()` to securely hand off the request execution payload natively to the HTML rendering pipeline.

You are expected to iterate. If the user sees the mock and asks for changes (e.g., "make it blue", "add more padding", "change the font"), you should acknowledge the request and call `generate_html_mock()` again to produce the updated version.
"""

async def compile_artifact_markdown(state_obj: SessionStateObj) -> dict:
    prompt = """
    You are an expert technical writer and Product Manager building requirement artifacts. 
    You are given the current raw memory state of an AI requirements elicitation session, including all locked decisions, assumptions, and the transcript context.
    
    Your job is to generate highly professional, cohesive Markdown documents synthesizing this data gracefully into paragraphs, structured bullet points, and tables where appropriate.
    
    Output strictly valid JSON with the following keys mapping to their exact markdown strings:
    - 'foundations_md': A robust document summarizing the high-level framework rules (Identity, Scale, etc).
    - 'assumptions_md': A distinct document organizing assumptions made heavily detailing rationale.
    - 'ui_spec_md': A document grouping all explicitly mapped UI variables under cleanly nested h2 elements per screen. Leave blank if layer context lacks robust screen spec items.
    
    Only output JSON.
    """
    
    state_dump = state_obj.model_dump_json(include={"layer", "brief", "decisions", "assumptions", "skipped", "transcript"})
    
    res = await openai_client.chat.completions.create(
        model="gpt-4o",
        response_format={ "type": "json_object" },
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Raw Payload:\n\n{state_dump}"}
        ]
    )
    
    try:
        return json.loads(res.choices[0].message.content)
    except:
        return {"foundations_md": "Error parsing output.", "assumptions_md": "", "ui_spec_md": ""}

async def compile_html_mock(state_obj: SessionStateObj) -> str:
    prompt = f"""
    You are a Senior Frontend Engineer compiling a raw, flawlessly formatted, single-file HTML mock application matching the provided Product Requirements.
    Embed high-end, responsive CSS mimicking a premium commercial app visually dynamically styling the framework natively via script tagging.
    Conform 100% strictly to the features mapped across the exact rules enclosed globally below without dropping edgecases!
    
    --- REQUIREMENTS ---
    FOUNDATIONS:
    {state_obj.artifacts.foundations_md or 'N/A'}
    
    UI SPECIFICATIONS:
    {state_obj.artifacts.ui_spec_md or 'N/A'}
    
    ASSUMPTIONS:
    {state_obj.artifacts.assumptions_md or 'N/A'}
    
    Do not output markdown codeblock ticks. Return ONLY the raw textual HTML string cleanly.
    """
    res = await openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt}]
    )
    
    out = res.choices[0].message.content.strip()
    if out.startswith("```html"): out = out[7:]
    if out.endswith("```"): out = out[:-3]
    return out.strip()

def update_session_state(session_id: str, state_obj: SessionStateObj):
    with Session(engine) as db_session:
        record = db_session.get(SessionRecord, session_id)
        if record:
            record.state_json = state_obj.model_dump_json()
            db_session.add(record)
            db_session.commit()

async def process_chat_stream(session_id: str, state_obj: SessionStateObj, user_message: str) -> AsyncGenerator[str, None]:
    # Append user message to transcript
    print(f"\n[USER MESSAGE] Session: {session_id} | Content: {user_message[:100]}...")
    state_obj.transcript.append({"role": "user", "content": user_message})
    update_session_state(session_id, state_obj)

    loop_count = 0
    max_loops = 5
    
    while loop_count < max_loops:
        loop_count += 1
        
        # We build the messages for OpenAI
        if state_obj.layer == 0:
            base_prompt = SYSTEM_PROMPT_L0
        elif state_obj.layer == 1:
            base_prompt = SYSTEM_PROMPT_L1
            if state_obj.artifacts.foundations_md:
                base_prompt += f"\n\n--- REQUIRED FOUNDATIONS CONSTANTS ---\n{state_obj.artifacts.foundations_md}"
        else:
            base_prompt = SYSTEM_PROMPT_L2
            if state_obj.artifacts.foundations_md:
                base_prompt += f"\n\n--- REQUIRED FOUNDATIONS CONSTANTS ---\n{state_obj.artifacts.foundations_md}"
            if state_obj.artifacts.ui_spec_md:
                base_prompt += f"\n\n--- REQUIRED UI SPECIFICATIONS ---\n{state_obj.artifacts.ui_spec_md}"

        messages = [{"role": "system", "content": base_prompt}]
        
        # Send current state in prompt (abbreviated for tokens)
        state_summary = f"Current State => Brief: '{state_obj.brief}' | Decisions count: {len(state_obj.decisions)}, Assumptions count: {len(state_obj.assumptions)}, Skipped count: {len(state_obj.skipped)}"
        messages.append({"role": "system", "content": state_summary})
        messages.extend(state_obj.transcript)

        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=AGENT_TOOLS,
            stream=True
        )
        
        assistant_msg_content = ""
        current_tool_calls = {}
        
        async for chunk in response:
            delta = chunk.choices[0].delta
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    tc_index = tc.index
                    if tc_index not in current_tool_calls:
                        current_tool_calls[tc_index] = {"name": tc.function.name, "arguments": ""}
                    if tc.function.arguments:
                        current_tool_calls[tc_index]["arguments"] += tc.function.arguments
            elif delta.content:
                assistant_msg_content += delta.content
                yield {"data": json.dumps({'type': 'text', 'content': delta.content})}
                
        # Handle the backend state update for tool calls
        if current_tool_calls:
            for tc in current_tool_calls.values():
                name = tc["name"]
                try:
                    args = json.loads(tc["arguments"])
                    print(f"  [TOOL CALL] Executing: {name} | Args: {args}")
                    
                    # Update state with tool call!
                    if name == "record_decision":
                        state_obj.decisions[args["item_id"]] = Decision(value=args["value"], source=args["source"])
                    elif name == "record_assumption":
                        state_obj.assumptions[args["item_id"]] = Assumption(value=args["value"], rationale=args["rationale"])
                    elif name == "mark_skipped":
                        state_obj.skipped[args["item_id"]] = Skipped(reason=args["reason"])
                    elif name == "finalize_layer":
                        yield {"data": json.dumps({'type': 'action', 'content': 'Compiling Product Documents via LLM... (This may take ~10 seconds)'})}
                        
                        compiled_md = await compile_artifact_markdown(state_obj)
                        state_obj.artifacts.foundations_md = compiled_md.get("foundations_md", state_obj.artifacts.foundations_md)
                        state_obj.artifacts.assumptions_md = compiled_md.get("assumptions_md", state_obj.artifacts.assumptions_md)
                        
                        if state_obj.layer == 0:
                            state_obj.layer = 1
                            print(f"  [LAYER TRANSITION] Layer 0 -> Layer 1")
                            escalation_prompt = "<System Update: Layer 0 Finalized. You are now the Layer 1 UI Spec Agent. DO NOT say goodbye. You MUST immediately begin Phase 1A by proposing a comprehensive list of UI screens for the application based on the user's brief. End your response by asking the user to confirm the screen inventory.>"
                        else:
                            state_obj.artifacts.ui_spec_md = compiled_md.get("ui_spec_md", state_obj.artifacts.ui_spec_md)
                            state_obj.layer = 2
                            print(f"  [LAYER TRANSITION] Layer 1 -> Layer 2")
                            escalation_prompt = "<System Update: Layer 1 Finalized. You are now the HTML Mock Agent (Layer 2). Do NOT say goodbye. Greet the user, summarize the specs briefly, and ask if they have any visual aesthetic requests before you generate the HTML mock.>"
                        
                        yield {"data": json.dumps({'type': 'action', 'content': 'Layer Finalized'})}
                        
                    elif name == "generate_html_mock":
                        print(f"  [MOCK GENERATION] Compiling HTML Mock...")
                        yield {"data": json.dumps({'type': 'action', 'content': 'Compiling HTML UI Mock via LLM... (This may take ~15 seconds)'})}
                        
                        state_obj.artifacts.html_mock = await compile_html_mock(state_obj)
                        # We stay in Layer 2 to allow for iterations and regenerations.
                        yield {"data": json.dumps({'type': 'action', 'content': 'HTML Mock Generated'})}
                        print(f"  [MOCK GENERATION] Success!")
                    
                    elif name == "update_artifacts":
                        print(f"  [ARTIFACT UPDATE] Re-compiling Markdown artifacts...")
                        yield {"data": json.dumps({'type': 'action', 'content': 'Updating Artifact Panels...'})}
                        compiled_md = await compile_artifact_markdown(state_obj)
                        state_obj.artifacts.foundations_md = compiled_md.get("foundations_md", state_obj.artifacts.foundations_md)
                        state_obj.artifacts.assumptions_md = compiled_md.get("assumptions_md", state_obj.artifacts.assumptions_md)
                        state_obj.artifacts.ui_spec_md = compiled_md.get("ui_spec_md", state_obj.artifacts.ui_spec_md)
                        yield {"data": json.dumps({'type': 'action', 'content': 'Artifacts Updated'})}
                        print(f"  [ARTIFACT UPDATE] Success!")
                    
                    state_obj.transcript.append({
                        "role": "assistant",
                        "content": f"[Tool Call Executed: {name} => {args.get('item_id', 'none')}]"
                    })
                    update_session_state(session_id, state_obj)
                    yield {"data": json.dumps({'type': 'tool_executed', 'name': name, 'arguments': args})}
                    
                except json.JSONDecodeError as e:
                    yield {"data": json.dumps({'type': 'error', 'content': 'Failed to parse tool arguments.', 'details': str(e)})}
            
            # Re-prompt the agent to keep talking after acting!
            if "finalize_layer" in [tc["name"] for tc in current_tool_calls.values()]:
                state_obj.transcript.append({
                    "role": "user",
                    "content": escalation_prompt
                })
            elif "generate_html_mock" in [tc["name"] for tc in current_tool_calls.values()]:
                state_obj.transcript.append({
                    "role": "user",
                    "content": "<System Update: HTML Mock successfully generated and saved to the user's Artifacts panel. Congratulate the user and conclude the interaction permanently.>"
                })
            else:
                state_obj.transcript.append({
                    "role": "user",
                    "content": "<System Update: Tool calls recorded. If the user wants to move on or you are completely finished, you MUST call the `finalize_layer` tool NOW instead of responding with text. Otherwise, review the results and ask your next questions.>"
                })
                
            update_session_state(session_id, state_obj)
            continue
            
        else:
            # Normal text finished, break out of stream completion loop
            state_obj.transcript.append({"role": "assistant", "content": assistant_msg_content})
            update_session_state(session_id, state_obj)
            break

    yield {"data": "[DONE]"}

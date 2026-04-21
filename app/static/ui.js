let currentSessionId = localStorage.getItem('sessionId') || null;

// UI Elements
const elOnboarding = document.getElementById('onboarding');
const elApp = document.getElementById('app-container');
const chatMessages = document.getElementById('chat-messages');

async function checkExistingSession() {
    await fetchAllPastSessions();
    if(currentSessionId) {
        // We could load the session explicitly, but we'll let the user pick it from history
    }
}
checkExistingSession();

const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const startForm = document.getElementById('start-form');
const toolsLog = document.getElementById('tools-log');

// State Monitoring
async function refreshState() {
    if (!currentSessionId) return;
    try {
        const res = await fetch(`/api/sessions/${currentSessionId}`);
        if(res.ok) {
            const state = await res.json();
            
            // Update Metrics
            document.getElementById('m-layer').textContent = state.layer;
            document.getElementById('m-decisions').textContent = Object.keys(state.decisions || {}).length;
            document.getElementById('m-assumptions').textContent = Object.keys(state.assumptions || {}).length;
            document.getElementById('m-skipped').textContent = Object.keys(state.skipped || {}).length;
            document.getElementById('brief-text').textContent = state.brief;
            
            // Map Database items into Drawer!
            const decList = document.getElementById('state-decisions-list');
            decList.innerHTML = '';
            for (const [key, val] of Object.entries(state.decisions || {})) {
                decList.innerHTML += `<li><strong style="color:var(--accent)">${key}</strong> <br/> ${val.value}</li>`;
            }
            
            const assList = document.getElementById('state-assumptions-list');
            assList.innerHTML = '';
            for (const [key, val] of Object.entries(state.assumptions || {})) {
                assList.innerHTML += `<li><strong style="color:var(--accent)">${key}</strong> <br/> ${val.value}</li>`;
            }
            
            // Update Markdown Viewer dynamically using marked
            if (state.artifacts) {
                if (state.artifacts.foundations_md) {
                    document.getElementById('foundations-content').innerHTML = marked.parse(state.artifacts.foundations_md);
                    document.getElementById('btn-download-foundations').classList.remove('hidden');
                    window.currentFoundationsContent = state.artifacts.foundations_md;
                }
                if (state.artifacts.ui_spec_md) {
                    document.getElementById('uispec-content').innerHTML = marked.parse(state.artifacts.ui_spec_md);
                    document.getElementById('btn-download-uispec').classList.remove('hidden');
                    window.currentUiSpecContent = state.artifacts.ui_spec_md;
                }
                if (state.artifacts.assumptions_md) {
                    document.getElementById('assumptions-content').innerHTML = `<h3>Assumptions</h3>` + marked.parse(state.artifacts.assumptions_md);
                }
                if (state.artifacts.html_mock) {
                    document.getElementById('code-htmlmock').textContent = state.artifacts.html_mock;
                    document.getElementById('btn-download-html').classList.remove('hidden');
                    window.currentHtmlMockContent = state.artifacts.html_mock; // cache globally for dl event
                    
                    // Update Iframe Preview
                    const iframe = document.getElementById('iframe-mock');
                    if (iframe && iframe.srcdoc !== state.artifacts.html_mock) {
                        iframe.srcdoc = state.artifacts.html_mock;
                    }
                }
            }
        }
    } catch(e) {
        console.error("State refresh error", e);
    }
}

// Append Chat Method
function appendChat(role, content) {
    const div = document.createElement('div');
    div.className = `msg ${role}`;
    
    if (role === 'agent') {
        const p = document.createElement('div');
        p.className = 'markdown-body';
        p.innerHTML = marked.parse(content);
        div.appendChild(p);
    } else {
        div.textContent = content; // User text is raw
    }
    
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return div;
}

function logToolEvent(name, payloadStr) {
    const list = document.getElementById('tools-log');
    if(!list) return;
    
    // Clear "No tool events" placeholder on first hit
    if (list.querySelector('em')) {
        list.innerHTML = '';
    }
    
    const li = document.createElement('li');
    li.innerHTML = `<strong>${name}</strong>: ${payloadStr}`;
    list.prepend(li);
}

// Session Creation Event - Simplified for User-First brief
document.getElementById('btn-start-quick').addEventListener('click', (e) => {
    e.preventDefault();
    currentSessionId = null;
    localStorage.removeItem('sessionId');
    
    // Reset UI to "New Session" state
    chatMessages.innerHTML = '';
    document.getElementById('chat-header-name').textContent = "New Session";
    document.getElementById('brief-text').textContent = "Enter your project brief below to begin...";
    chatInput.placeholder = "Describe your project (e.g., 'Build a simple Todo app')...";
    chatInput.disabled = false;
    
    // Add a welcome hint
    const div = document.createElement('div');
    div.className = 'msg ai';
    div.innerHTML = `<div class="markdown-body"><p>Welcome to <strong>Heart Wood</strong>. What would you like to build today? Please provide a brief description to start laying the first ring.</p></div>`;
    chatMessages.appendChild(div);
});

// Removed btn-resume explicit listener

async function loadSessionExplicit(sessionId) {
    currentSessionId = sessionId;
    localStorage.setItem('sessionId', sessionId);
    
    chatMessages.innerHTML = '';
    
    // Disable input while loading
    const input = document.getElementById('chat-input');
    input.disabled = true;
    input.placeholder = "Loading session...";
    
    try {
        const res = await fetch(`/api/sessions/${currentSessionId}`);
        if(res.ok) {
            const state = await res.json();
            console.log("Session Loaded Successfully:", state);
            
            // Clean up old chat messages
            chatMessages.innerHTML = '';
            document.getElementById('chat-header-name').textContent = state.name || "New Project";
            
            for(let msg of state.transcript) {
                const content = msg.content || "";
                
                // Skip internal system/engine messages for a cleaner UI
                if(msg.role === 'system') continue;
                if(content.startsWith('<System Update:')) continue;
                
                const roleClass = (msg.role === 'user') ? 'user' : 'ai';
                
                // Handle Tool Execution Logs separately (Move to Sidebar, Hide from Chat)
                if (content.startsWith('[Tool Call Executed:')) {
                    logToolEvent('Historical Tool', content);
                    continue; 
                }
                
                const msgBlock = document.createElement('div');
                msgBlock.className = `msg ${roleClass}`;
                
                const markdownContainer = document.createElement('div');
                markdownContainer.className = 'markdown-body';
                markdownContainer.innerHTML = marked.parse(content);
                msgBlock.appendChild(markdownContainer);
                
                chatMessages.appendChild(msgBlock);
            }
            chatMessages.scrollTop = chatMessages.scrollHeight;
            refreshState();
        }
    } catch(e) {
        console.error("Critical Load Error:", e);
        localStorage.removeItem('sessionId');
        currentSessionId = null;
    } finally {
        input.disabled = false;
        input.placeholder = "Message Heart Wood...";
    }
}

async function fetchAllPastSessions() {
    try {
        const res = await fetch('/api/sessions');
        if (!res.ok) return;
        const sessions = await res.json();
        
        if (sessions.length > 0) {
            const listContainer = document.getElementById('sessions-list');
            listContainer.innerHTML = '';
            
            sessions.forEach(s => {
                const item = document.createElement('div');
                item.style.padding = '10px';
                item.style.background = 'rgba(0,0,0,0.2)';
                item.style.borderRadius = '6px';
                item.style.cursor = 'pointer';
                item.style.border = '1px solid var(--border-glass)';
                item.style.fontSize = '14px';
                item.innerHTML = `<strong style="color:var(--accent);">L${s.layer}</strong> <span style="font-weight:500; margin-left:6px;">${s.name || "New Project"}</span>`;
                
                item.addEventListener('mouseenter', () => item.style.border = '1px solid var(--accent)');
                item.addEventListener('mouseleave', () => item.style.border = '1px solid var(--border-glass)');
                item.addEventListener('click', () => loadSessionExplicit(s.id));
                listContainer.appendChild(item);
            });
        }
    } catch(e) {
        console.error("Failed loading history", e);
    }
}

// Chat Output Stream Logic
chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const msg = chatInput.value;
    if(!msg) return;
    
    // Handle Session Creation on First Message
    if (!currentSessionId) {
        try {
            const res = await fetch('/api/sessions', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ brief: msg, layer: 0 })
            });
            if (res.ok) {
                const sessionData = await res.json();
                currentSessionId = sessionData.id;
                localStorage.setItem('sessionId', currentSessionId);
                document.getElementById('chat-header-name').textContent = sessionData.name || "New Project";
                document.getElementById('brief-text').textContent = msg;
                await fetchAllPastSessions();
            } else {
                alert("Failed to create session. Please try again.");
                return;
            }
        } catch (err) {
            console.error("Session creation error:", err);
            return;
        }
    }
    
    appendChat('user', msg);
    chatInput.value = '';
    chatInput.placeholder = "Message Heart Wood...";
    
    // Run SSE fetch via native fetch loop using manual chunk parsing
    submitChatStream(msg);
});

async function submitChatStream(msg) {
    const response = await fetch(`${API_BASE}/${currentSessionId}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg })
    });
    
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    
    // Show Loading/Typing Indicator
    const loadingBlock = document.createElement('div');
    loadingBlock.className = 'msg ai loading-indicator';
    loadingBlock.innerHTML = `<div class="typing-loader"><span></span><span></span><span></span></div>`;
    chatMessages.appendChild(loadingBlock);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    let msgBlock = null;
    let markdownContainer = null;
    let activeTextBuffer = "";
    let streamBuffer = "";
    let isFirstPacket = true;
    
    // Proper SSE unwrap logic inside fetch stream
    while(true) {
        const { value, done } = await reader.read();
        if (done) break;
        
        streamBuffer += decoder.decode(value, {stream: true});
        let blocks = streamBuffer.split(/\r?\n\r?\n/);
        streamBuffer = blocks.pop();
        
        for(let block of blocks) {
            block = block.trim();
            if(!block) continue;
            
            if (block.startsWith("data:")) {
                let jsonStr = block.substring(5).trim();
                console.log("SSE Stream Event:", jsonStr);
                if(jsonStr === "[DONE]") {
                    if(msgBlock) msgBlock.classList.remove('streaming');
                    break;
                }
                
                try {
                    let d = JSON.parse(jsonStr);
                    
                    // Remove loader upon first data event
                    if (isFirstPacket) {
                        if (loadingBlock) loadingBlock.remove();
                        isFirstPacket = false;
                        
                        // Create the real message block
                        msgBlock = document.createElement('div');
                        msgBlock.className = `msg ai streaming`;
                        markdownContainer = document.createElement('div');
                        markdownContainer.className = 'markdown-body';
                        msgBlock.appendChild(markdownContainer);
                        chatMessages.appendChild(msgBlock);
                    }
                    
                    if (d.type === 'text') {
                        activeTextBuffer += d.content;
                        markdownContainer.innerHTML = marked.parse(activeTextBuffer);
                    } else if (d.type === 'tool_executed') {
                        logToolEvent(d.name, JSON.stringify(d.arguments));
                        refreshState();
                    } else if (d.type === 'action') {
                        logToolEvent('Action Called', d.content);
                        refreshState();
                    } else if (d.type === 'error') {
                        logToolEvent('Error', d.content);
                    }
                } catch(e) {
                    console.error("Parse Error:", jsonStr, e);
                }
            }
        }
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
}

// Tab Listeners
document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', (e) => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.add('hidden'));
        e.target.classList.add('active');
        document.getElementById(e.target.dataset.target).classList.remove('hidden');
    });
});

// HTML Mock View Toggles
document.getElementById('btn-view-preview').addEventListener('click', () => {
    document.getElementById('btn-view-preview').classList.add('active');
    document.getElementById('btn-view-code').classList.remove('active');
    document.getElementById('mock-preview-container').classList.remove('hidden');
    document.getElementById('mock-code-container').classList.add('hidden');
});
document.getElementById('btn-view-code').addEventListener('click', () => {
    document.getElementById('btn-view-code').classList.add('active');
    document.getElementById('btn-view-preview').classList.remove('active');
    document.getElementById('mock-code-container').classList.remove('hidden');
    document.getElementById('mock-preview-container').classList.add('hidden');
});

// HTML Mock Download Hook
document.getElementById('btn-download-html').addEventListener('click', () => {
    if(!window.currentHtmlMockContent) return;
    downloadFile(window.currentHtmlMockContent, 'mock.html', 'text/html');
});

// Foundations Download
document.getElementById('btn-download-foundations').addEventListener('click', () => {
    if(!window.currentFoundationsContent) return;
    downloadFile(window.currentFoundationsContent, 'foundations.md', 'text/markdown');
});

// UI Spec Download
document.getElementById('btn-download-uispec').addEventListener('click', () => {
    if(!window.currentUiSpecContent) return;
    downloadFile(window.currentUiSpecContent, 'ui_spec.md', 'text/markdown');
});

function downloadFile(content, filename, type) {
    const blob = new Blob([content], {type});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${currentSessionId ? currentSessionId.substring(0,8) : 'export'}_${filename}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// Rename Session logic
document.getElementById('btn-rename-session').addEventListener('click', async () => {
    if(!currentSessionId) return;
    const newName = prompt("Rename this project session:");
    if(!newName) return;
    try {
        const res = await fetch(`/api/sessions/${currentSessionId}/name`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: newName })
        });
        if(res.ok) {
            document.getElementById('chat-header-name').textContent = newName;
            await fetchAllPastSessions();
        }
    } catch(e) {
        console.error("Rename API failed", e);
    }
});

// Delete Session logic
document.getElementById('btn-delete-session').addEventListener('click', async () => {
    if(!currentSessionId) return;
    if(!confirm("Are you sure you want to permanently delete this project session?")) return;
    try {
        const res = await fetch(`/api/sessions/${currentSessionId}`, { method: 'DELETE' });
        if(res.ok) {
            currentSessionId = null;
            localStorage.removeItem('sessionId');
            document.getElementById('chat-messages').innerHTML = '';
            document.getElementById('chat-header-name').textContent = "Elicitation Chat";
            document.getElementById('brief-text').textContent = "Select a session...";
            await fetchAllPastSessions();
        }
    } catch(e) {
        console.error("Delete API failed", e);
    }
});

// Restart Session
// We didn't keep a dedicated Restart Button but if we want to reset UI locally:
/* document.getElementById('btn-restart').addEventListener('click', () => {
    currentSessionId = null;
    localStorage.removeItem('sessionId');
    chatMessages.innerHTML = '';
    checkExistingSession(); 
}); */

// Legacy floating Drawer Toggles logic permanently removed

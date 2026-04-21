import json
from sqlmodel import Session, select
from app.database import engine
from app.models import SessionRecord, SessionStateObj
from app.services.llm_agent import generate_ui_spec_md

with Session(engine) as db_session:
    records = db_session.exec(select(SessionRecord)).all()
    for record in records:
        state_dict = json.loads(record.state_json)
        state_obj = SessionStateObj(**state_dict)
        if state_obj.layer >= 1:
            state_obj.artifacts.ui_spec_md = generate_ui_spec_md(state_obj)
            record.state_json = state_obj.model_dump_json()
            db_session.add(record)
    db_session.commit()
print("UI Specs successfully recompiled retroactively!")

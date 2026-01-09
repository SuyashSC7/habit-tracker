import streamlit as st
from datetime import date, timedelta
import subprocess
import json

from sqlalchemy import (
    create_engine, Column, Integer, String,
    Boolean, Date
)
from sqlalchemy.orm import declarative_base, sessionmaker
import pandas as pd

# ------------------ PAGE SETUP ------------------
st.set_page_config(page_title="Habit Tracker", page_icon="🔥")
st.title("🔥 Habit Tracker with AI Coach")

# ------------------ DATABASE SETUP ------------------
engine = create_engine("sqlite:///habits.db")
Session = sessionmaker(bind=engine)
db = Session()
Base = declarative_base()


class Habit(Base):
    __tablename__ = "habits"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    frequency = Column(String, nullable=False)


class CheckIn(Base):
    __tablename__ = "checkins"
    id = Column(Integer, primary_key=True)
    habit_id = Column(Integer)
    day = Column(Date)
    done = Column(Boolean)


Base.metadata.create_all(engine)

today = date.today()

# ------------------ LLM FUNCTION ------------------
def ask_coach(prompt: str) -> str:
    """
    Uses local LLM via Ollama - optimized for speed
    """
    try:
        # Use a faster, lighter model or add parameters for quick response
        result = subprocess.run(
            ["ollama", "run", "deepseek-coder", "--verbose", "false"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=15  # Reduced timeout
        )
        output = result.stdout.strip()
        return output if output else "⚠️ No response received. Try again."
    except subprocess.TimeoutExpired:
        return "⚠️ Response took too long. Consider using a lighter model like 'llama2' or 'mistral'."
    except Exception as e:
        return f"⚠️ Error: {str(e)}\n\nTry: ollama pull mistral (for faster responses)"


# ------------------ ADD HABIT (BUTTON + MODAL) ------------------
if st.button("➕ Add New Habit", type="primary"):
    st.session_state.show_add_form = True

if st.session_state.get('show_add_form', False):
    with st.form("habit_form"):
        st.subheader("Add a New Habit")
        habit_name = st.text_input("Habit name")
        frequency = st.selectbox("Frequency", ["Daily", "Weekly"])
        col1, col2 = st.columns(2)
        
        with col1:
            submitted = st.form_submit_button("Save Habit")
        with col2:
            cancel = st.form_submit_button("Cancel")

        if submitted and habit_name.strip():
            db.add(Habit(name=habit_name.strip(), frequency=frequency))
            db.commit()
            st.success("Habit saved!")
            st.session_state.show_add_form = False
            st.rerun()
        
        if cancel:
            st.session_state.show_add_form = False
            st.rerun()

# ------------------ DAILY CHECK-IN ------------------
st.subheader("✅ Today's Check-in")

habits = db.query(Habit).all()

if not habits:
    st.info("No habits yet. Click 'Add New Habit' above to get started.")
else:
    for habit in habits:
        col1, col2 = st.columns([4, 1])
        
        with col1:
            checkin = db.query(CheckIn).filter_by(
                habit_id=habit.id,
                day=today
            ).first()

            checked = checkin.done if checkin else False

            done = st.checkbox(
                habit.name,
                value=checked,
                key=f"habit_{habit.id}"
            )

            if done and not checkin:
                db.add(CheckIn(habit_id=habit.id, day=today, done=True))
                db.commit()

            if not done and checkin:
                checkin.done = False
                db.commit()
        
        with col2:
            if st.button("🗑️", key=f"delete_{habit.id}", help="Delete habit"):
                # Delete all check-ins for this habit
                db.query(CheckIn).filter_by(habit_id=habit.id).delete()
                # Delete the habit
                db.query(Habit).filter_by(id=habit.id).delete()
                db.commit()
                st.rerun()

# ------------------ STREAK CALCULATION (TABLE FORMAT) ------------------
st.subheader("🔥 Habit Streaks")

streak_data = []

if habits:
    for habit in habits:
        history = (
            db.query(CheckIn)
            .filter_by(habit_id=habit.id)
            .order_by(CheckIn.day.desc())
            .all()
        )

        streak = 0
        expected_day = today

        for checkin in history:
            if checkin.day == expected_day and checkin.done:
                streak += 1
                expected_day -= timedelta(days=1)
            else:
                break

        # Calculate total completions
        total_done = sum(1 for c in history if c.done)
        
        streak_data.append({
            "Habit": habit.name,
            "Current Streak": f"{streak} 🔥",
            "Total Completed": total_done,
            "Frequency": habit.frequency
        })

    # Display as table
    df = pd.DataFrame(streak_data)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # ------------------ WEEKLY CALENDAR VIEW ------------------
    st.subheader("📅 Weekly Calendar View")
    
    # Get last 7 days
    week_days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    
    calendar_data = []
    
    for habit in habits:
        row = {"Habit": habit.name}
        
        for day in week_days:
            checkin = db.query(CheckIn).filter_by(
                habit_id=habit.id,
                day=day
            ).first()
            
            if checkin and checkin.done:
                row[day.strftime("%a %m/%d")] = "✅"
            else:
                row[day.strftime("%a %m/%d")] = "⬜"
        
        calendar_data.append(row)
    
    if calendar_data:
        calendar_df = pd.DataFrame(calendar_data)
        st.dataframe(calendar_df, use_container_width=True, hide_index=True)
else:
    st.info("No habits to display.")

# ------------------ AI COACH ------------------
st.subheader("🤖 AI Habit Coach")

col1, col2 = st.columns([3, 1])

with col1:
    if st.button("Get Quick Health Insights", type="secondary"):
        if not habits:
            st.info("Add habits first.")
        else:
            # Build concise habit summary
            habit_list = [f"{item['Habit']} ({item['Current Streak'].replace(' 🔥', '')} days)" for item in streak_data]
            habit_summary = ", ".join(habit_list)

            prompt = f"""You are a health coach. Give brief advice (max 5 sentences) with specific health stats.

Habits: {habit_summary}

For each habit type (exercise/meditation/reading etc), state ONE key health benefit with a percentage or stat. Be concise and encouraging."""

            with st.spinner("Analyzing..."):
                response = ask_coach(prompt)

            if response:
                st.markdown("### 💡 Health Insights")
                st.write(response)
            else:
                st.warning("No response. Ensure Ollama is running: `ollama run mistral`")

with col2:
    with st.expander("⚙️ Model"):
        st.caption("Using: deepseek-coder")
        st.caption("For faster results, try:")
        st.code("ollama pull mistral", language="bash")
        st.code("ollama pull llama2", language="bash")

# ------------------ FOOTER ------------------
st.markdown("---")
st.caption("Local AI • Offline • Privacy Friendly")
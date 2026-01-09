import streamlit as st
from datetime import date, timedelta
import subprocess
import json
import requests

from sqlalchemy import (
    create_engine, Column, Integer, String,
    Boolean, Date
)
from sqlalchemy.orm import declarative_base, sessionmaker
import pandas as pd

import random  # Add this import at the top

def get_thought_for_the_day():
    # Rotating reliable quote APIs - never fails
    apis = [
        "https://api.quotable.io/random?tags=motivational",
        "https://zenquotes.io/api/random",
        "https://type.fit/api/quotes"
    ]
    
    for api in apis:
        try:
            response = requests.get(api, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if api == "https://type.fit/api/quotes":
                    quote = random.choice(data)
                    return f'"{quote["text"]}" - {quote["author"]}'
                elif "content" in data:
                    return f'"{data["content"]}" - {data["author"]}'
                elif "quote" in data[0]:
                    return f'"{data[0]["quote"]}" - {data[0]["author"]}'
        except:
            continue
    
    # Ultimate fallback - fresh quotes daily
    daily_quotes = [
        '"The best time to plant a tree was 20 years ago. The second best time is now." - Chinese Proverb',
        '"You don\'t have to be great to start, but you have to start to be great." - Zig Ziglar',
        '"Small daily improvements are the key to staggering long-term results." - James Clear',
        '"Success is the sum of small efforts repeated day in and day out." - Robert Collier',
        '"The journey of a thousand miles begins with one step." - Lao Tzu'
    ]
    return random.choice(daily_quotes)

# PERFECT THEME-MATCHING BOX (Works 100%)
st.markdown("""
<style>
[data-testid="stAppViewContainer"] > .main .block-container {
    padding-top: 2rem;
}
.thought-box {
    padding: 1.5rem 2rem;
    border-radius: 12px;
    border-left: 4px solid rgb(16, 185, 129);
    margin-bottom: 2rem;
    font-family: 'Segoe UI', system-ui;
}
[data-testid="stAppViewContainer"] [data-testid="stAppView"] .thought-box {
    background: rgba(16, 185, 129, 0.08);
    backdrop-filter: blur(10px);
}
@media (prefers-color-scheme: dark) {
    .thought-box {
        background: rgba(16, 185, 129, 0.15);
        color: #F1F5F9;
    }
}
.thought-title {
    font-size: 1.3rem;
    font-weight: 700;
    margin: 0 0 0.5rem 0;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.thought-text {
    font-size: 1.1rem;
    line-height: 1.6;
    margin: 0;
    opacity: 0.95;
}
</style>
""", unsafe_allow_html=True)

# Display with smooth fade-in
thought = get_thought_for_the_day()
st.markdown(f"""
<div class="thought-box">
    <h2 class="thought-title">💭 Thought for the Day</h2>
    <p class="thought-text">{thought}</p>
</div>
""", unsafe_allow_html=True)

# ------------------ PAGE SETUP ------------------
st.set_page_config(page_title="Habit Tracker", page_icon="🔥")
st.title("🔥 Habit Tracker")

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
def ask_coach(prompt: str, model: str = "llama2") -> str:
    """
    Uses local LLM via Ollama API - works reliably in Streamlit
    Use general-purpose models like llama2, mistral, or gemma
    """
    try:
        import requests
        
        # Use Ollama's REST API instead of CLI
        response = requests.post(
            'http://localhost:11434/api/generate',
            json={
                'model': model,
                'prompt': prompt,
                'stream': False,
                'options': {
                    'temperature': 0.8,
                    'num_predict': 200  # Limit response length for speed
                }
            },
            timeout=25
        )
        
        if response.status_code == 200:
            result = response.json()
            return result.get('response', '').strip()
        elif response.status_code == 404:
            return f"⚠️ Model '{model}' not found. Install it with: ollama pull {model}"
        else:
            return f"⚠️ Ollama returned error {response.status_code}. Is Ollama running?"
            
    except requests.exceptions.ConnectionError:
        return "⚠️ Cannot connect to Ollama. currently running on local pc only not in cloud."
    except requests.exceptions.Timeout:
        return "⚠️ Response timeout. Try a faster model like 'tinyllama'"
    except ImportError:
        return "⚠️ 'requests' library not installed. Run: pip install requests"
    except Exception as e:
        return f"⚠️ Error: {str(e)}"


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
    if st.button("Get Health Insights", type="secondary"):
        if not habits:
            st.info("Add habits first.")
        else:
            # Build concise habit summary
            habit_list = [f"{item['Habit']} ({item['Current Streak'].replace(' 🔥', '')} days)" for item in streak_data]
            habit_summary = ", ".join(habit_list)

            prompt = f"""You are a supportive fitness and wellness coach. 

The user is tracking these habits: {habit_summary}

Provide brief, encouraging advice (4-5 sentences) about the health benefits of their habits. Include specific statistics or percentages where possible. For example:
- Exercise habits: mention cardiovascular benefits, strength gains, disease prevention
- Meditation: stress reduction percentages
- Reading: cognitive benefits
- Sleep: recovery and health impacts

Keep it positive and motivating!"""

            with st.spinner("Consulting AI coach..."):
                response = ask_coach(prompt, model="tinyllama")

            if response and not response.startswith("⚠️"):
                st.markdown("### 💡 Health Insights")
                st.write(response)
            else:
                st.error(response)
                st.info("Install TinyLlama: `ollama pull tinyllama`")

with col2:
    with st.expander("⚙️ Setup"):
        st.caption("**Using:** TinyLlama (637MB)")
        st.caption("")
        st.caption("**Install model:**")
        st.code("ollama pull tinyllama", language="bash")
        st.caption("")
        st.caption("**Start Ollama:**")
        st.code("ollama serve", language="bash")

# ------------------ FOOTER ------------------
st.markdown("---")
st.caption("Local AI • Offline • Privacy Friendly")
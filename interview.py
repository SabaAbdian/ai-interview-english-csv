import config 
import streamlit as st
import time
import os
from utils import (
    check_password,
    check_if_interview_completed,
    save_interview_data,
)

# Load API library
if "gpt" in config.MODEL.lower():
    api = "openai"
    from openai import OpenAI
elif "claude" in config.MODEL.lower():
    api = "anthropic"
    import anthropic
else:
    raise ValueError("Model does not contain 'gpt' or 'claude'; unable to determine API.")

# Set page title and icon
st.set_page_config(page_title="Interview", page_icon=config.AVATAR_INTERVIEWER)

# RTL support for Persian
st.markdown("""
    <style>
    body { direction: rtl; text-align: right; font-family: "Vazir", sans-serif; }
    .stChatMessage { direction: rtl !important; text-align: right !important; }
    </style>
""", unsafe_allow_html=True)

# Password login
if config.LOGINS:
    pwd_correct, username = check_password()
    if not pwd_correct:
        st.stop()
    else:
        st.session_state.username = username
else:
    st.session_state.username = "testaccount"

# Ensure necessary folders exist
for path in [config.TRANSCRIPTS_DIRECTORY, config.TIMES_DIRECTORY, config.BACKUPS_DIRECTORY]:
    if not os.path.exists(path):
        os.makedirs(path)

# Initialize session state
if "interview_active" not in st.session_state:
    st.session_state.interview_active = True
if "messages" not in st.session_state:
    st.session_state.messages = []
if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()
    st.session_state.start_time_file_names = time.strftime("%Y_%m_%d_%H_%M_%S", time.localtime(st.session_state.start_time))

# Check if already completed
if check_if_interview_completed(config.TIMES_DIRECTORY, st.session_state.username) and not st.session_state.messages:
    st.session_state.interview_active = False
    st.markdown("Interview already completed.")

# Quit button
col1, col2 = st.columns([0.85, 0.15])
with col2:
    if st.session_state.interview_active and st.button("Quit", help="End the interview."):
        st.session_state.interview_active = False
        quit_msg = "You have cancelled the interview."
        st.session_state.messages.append({"role": "assistant", "content": quit_msg})
        save_interview_data(
            username=st.session_state.username,
            transcripts_dir=config.TRANSCRIPTS_DIRECTORY,
            times_dir=config.TIMES_DIRECTORY,
        )

# Show existing conversation
for message in st.session_state.messages:
    if not any(code in message["content"] for code in config.CLOSING_MESSAGES.keys()):
        with st.chat_message(message["role"], avatar=(config.AVATAR_INTERVIEWER if message["role"] == "assistant" else config.AVATAR_RESPONDENT)):
            st.markdown(message["content"])

# Load model client
if api == "openai":
    client = OpenAI(api_key=st.secrets["API_KEY_OPENAI"])
    api_kwargs = {
        "model": config.MODEL,
        "messages": st.session_state.messages,
        "max_tokens": config.MAX_OUTPUT_TOKENS,
        "stream": True,
    }
    if config.TEMPERATURE is not None:
        api_kwargs["temperature"] = config.TEMPERATURE

elif api == "anthropic":
    client = anthropic.Anthropic(api_key=st.secrets["API_KEY_ANTHROPIC"])
    api_kwargs = {
        "system": config.SYSTEM_PROMPT,
        "messages": st.session_state.messages,
        "model": config.MODEL,
        "max_tokens": config.MAX_OUTPUT_TOKENS,
    }

# Start interview
if not st.session_state.messages:
    if api == "openai":
        with st.chat_message("assistant", avatar=config.AVATAR_INTERVIEWER):
            stream = client.chat.completions.create(**api_kwargs)
            first_msg = st.write_stream(stream)
        st.session_state.messages.append({"role": "assistant", "content": first_msg})

    elif api == "anthropic":
        st.session_state.messages.append({"role": "user", "content": "Hi"})
        with st.chat_message("assistant", avatar=config.AVATAR_INTERVIEWER):
            placeholder = st.empty()
            msg = ""
            with client.messages.stream(**api_kwargs) as stream:
                for delta in stream.text_stream:
                    if delta: msg += delta
                    placeholder.markdown(f'<div style="direction: rtl; text-align: right;">{msg}▌</div>', unsafe_allow_html=True)
            placeholder.markdown(f'<div style="direction: rtl; text-align: right;">{msg}</div>', unsafe_allow_html=True)
        st.session_state.messages.append({"role": "assistant", "content": msg})

    save_interview_data(
        username=st.session_state.username,
        transcripts_dir=config.BACKUPS_DIRECTORY,
        times_dir=config.BACKUPS_DIRECTORY,
    )

# Chat loop
if st.session_state.interview_active:
    if user_input := st.chat_input("Your message here"):
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user", avatar=config.AVATAR_RESPONDENT):
            st.markdown(user_input)

        with st.chat_message("assistant", avatar=config.AVATAR_INTERVIEWER):
            placeholder = st.empty()
            reply = ""

            if api == "openai":
                stream = client.chat.completions.create(**api_kwargs)
                for m in stream:
                    delta = m.choices[0].delta.content
                    if delta: reply += delta
                    if len(reply) > 5: placeholder.markdown(reply + "▌")
                    if any(code in reply for code in config.CLOSING_MESSAGES): break

            elif api == "anthropic":
                with client.messages.stream(**api_kwargs) as stream:
                    for delta in stream.text_stream:
                        if delta: reply += delta
                        if len(reply) > 5: placeholder.markdown(reply + "▌")
                        if any(code in reply for code in config.CLOSING_MESSAGES): break

            if not any(code in reply for code in config.CLOSING_MESSAGES):
                placeholder.markdown(reply)
                st.session_state.messages.append({"role": "assistant", "content": reply})
                try:
                    save_interview_data(
                        username=st.session_state.username,
                        transcripts_dir=config.TRANSCRIPTS_DIRECTORY,
                        times_dir=config.TIMES_DIRECTORY,
                    )
                except Exception as e:
                    print("⚠️ Failed to save data:", e)

            for code in config.CLOSING_MESSAGES:
                if code in reply:
                    st.session_state.messages.append({"role": "assistant", "content": reply})
                    st.session_state.interview_active = False
                    closing_msg = config.CLOSING_MESSAGES[code]
                    st.markdown(closing_msg)
                    st.session_state.messages.append({"role": "assistant", "content": closing_msg})

                    final_transcript_stored = False
                    while not final_transcript_stored:
                        save_interview_data(
                            username=st.session_state.username,
                            transcripts_dir=config.TRANSCRIPTS_DIRECTORY,
                            times_dir=config.TIMES_DIRECTORY,
                        )
                        final_transcript_stored = check_if_interview_completed(config.TRANSCRIPTS_DIRECTORY, st.session_state.username)
                        time.sleep(0.1)

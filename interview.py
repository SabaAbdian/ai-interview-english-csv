import streamlit as st
import time
import os
import csv
import pickle
from utils import (
    check_password,
    check_if_interview_completed,
    save_interview_data,
)
import config

# Load API library
if "gpt" in config.MODEL.lower():
    api = "openai"
    from openai import OpenAI
elif "claude" in config.MODEL.lower():
    api = "anthropic"
    import anthropic
else:
    raise ValueError("Model must contain 'gpt' or 'claude'.")

# Set up page
st.set_page_config(page_title="Interview", page_icon=config.AVATAR_INTERVIEWER)

# Auth
if config.LOGINS:
    pwd_correct, username = check_password()
    if not pwd_correct:
        st.stop()
    st.session_state.username = username
else:
    st.session_state.username = "testaccount"

# Create directories
os.makedirs("data", exist_ok=True)
for folder in [config.TRANSCRIPTS_DIRECTORY, config.TIMES_DIRECTORY, config.BACKUPS_DIRECTORY]:
    os.makedirs(folder, exist_ok=True)

# Per-user file
CSV_FILE_PATH = f"data/interview_data_{st.session_state.username}_{time.strftime('%Y_%m_%d_%H_%M_%S')}.csv"
if not os.path.exists(CSV_FILE_PATH):
    with open(CSV_FILE_PATH, mode="w", newline="") as file:
        csv.writer(file).writerow(["Timestamp", "Username", "Role", "Message"])

# Master file
MASTER_CSV_PATH = "data/interview_master.csv"
if not os.path.exists(MASTER_CSV_PATH):
    with open(MASTER_CSV_PATH, mode="w", newline="") as file:
        csv.writer(file).writerow(["Timestamp", "Username", "Role", "Message"])

def save_to_csv(role, message):
    row = [time.strftime('%Y-%m-%d %H:%M:%S'), st.session_state.username, role, message]
    with open(CSV_FILE_PATH, mode="a", newline="") as file:
        csv.writer(file).writerow(row)
    with open(MASTER_CSV_PATH, mode="a", newline="") as master_file:
        csv.writer(master_file).writerow(row)

# Session state setup
st.session_state.setdefault("interview_active", True)
st.session_state.setdefault("messages", [])
if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()
    st.session_state.start_time_file_names = time.strftime("%Y_%m_%d_%H_%M_%S", time.localtime(st.session_state.start_time))

# Early exit if already completed
if check_if_interview_completed(config.TIMES_DIRECTORY, st.session_state.username) and not st.session_state.messages:
    st.session_state.interview_active = False
    st.markdown("Interview already completed.")

# Quit button
if st.session_state.interview_active:
    with st.columns([0.85, 0.15])[1]:
        if st.button("Quit", help="End the interview."):
            st.session_state.interview_active = False
            msg = "You have cancelled the interview."
            st.session_state.messages.append({"role": "assistant", "content": msg})
            save_to_csv("assistant", msg)
            save_interview_data(st.session_state.username, config.TRANSCRIPTS_DIRECTORY, config.TIMES_DIRECTORY)

# Show past messages
for m in st.session_state.messages[1:]:
    if not any(code in m["content"] for code in config.CLOSING_MESSAGES.keys()):
        with st.chat_message(m["role"], avatar=config.AVATAR_INTERVIEWER if m["role"] == "assistant" else config.AVATAR_RESPONDENT):
            st.markdown(m["content"])

# Load model
if api == "openai":
    client = OpenAI(api_key=st.secrets["API_KEY_OPENAI"])
    api_kwargs = {"stream": True}
elif api == "anthropic":
    client = anthropic.Anthropic(api_key=st.secrets["API_KEY_ANTHROPIC"])
    api_kwargs = {"system": config.SYSTEM_PROMPT}
api_kwargs.update({
    "messages": st.session_state.messages,
    "model": config.MODEL,
    "max_tokens": config.MAX_OUTPUT_TOKENS,
})
if config.TEMPERATURE is not None:
    api_kwargs["temperature"] = config.TEMPERATURE

# First message
if not st.session_state.messages:
    if api == "openai":
        st.session_state.messages.append({"role": "system", "content": config.SYSTEM_PROMPT})
        with st.chat_message("assistant", avatar=config.AVATAR_INTERVIEWER):
            stream = client.chat.completions.create(**api_kwargs)
            first_response = st.write_stream(stream)
    elif api == "anthropic":
        st.session_state.messages.append({"role": "user", "content": "Hi"})
        with st.chat_message("assistant", avatar=config.AVATAR_INTERVIEWER):
            first_response = ""
            message_placeholder = st.empty()
            with client.messages.stream(**api_kwargs) as stream:
                for delta in stream.text_stream:
                    if delta:
                        first_response += delta
                    message_placeholder.markdown(first_response + "▌")
            message_placeholder.markdown(first_response)
    st.session_state.messages.append({"role": "assistant", "content": first_response})
    save_to_csv("assistant", first_response)
    save_interview_data(st.session_state.username, config.BACKUPS_DIRECTORY, config.BACKUPS_DIRECTORY,
                        f"_transcript_started_{st.session_state.start_time_file_names}",
                        f"_time_started_{st.session_state.start_time_file_names}")

# Chat loop
if st.session_state.interview_active:
    if user_msg := st.chat_input("Your message here"):
        st.session_state.messages.append({"role": "user", "content": user_msg})
        save_to_csv("user", user_msg)
        with st.chat_message("user", avatar=config.AVATAR_RESPONDENT):
            st.markdown(user_msg)

        save_interview_data(st.session_state.username, config.TRANSCRIPTS_DIRECTORY, config.TIMES_DIRECTORY)

        with st.chat_message("assistant", avatar=config.AVATAR_INTERVIEWER):
            message_placeholder = st.empty()
            reply = ""
            if api == "openai":
                stream = client.chat.completions.create(**api_kwargs)
                for chunk in stream:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        reply += delta
                    if len(reply) > 5:
                        message_placeholder.markdown(reply + "▌")
                    if any(code in reply for code in config.CLOSING_MESSAGES.keys()):
                        message_placeholder.empty()
                        break
            elif api == "anthropic":
                with client.messages.stream(**api_kwargs) as stream:
                    for delta in stream.text_stream:
                        if delta:
                            reply += delta
                        if len(reply) > 5:
                            message_placeholder.markdown(reply + "▌")
                        if any(code in reply for code in config.CLOSING_MESSAGES.keys()):
                            message_placeholder.empty()
                            break

            if not any(code in reply for code in config.CLOSING_MESSAGES.keys()):
                message_placeholder.markdown(reply)
                st.session_state.messages.append({"role": "assistant", "content": reply})
                save_to_csv("assistant", reply)
                try:
                    save_interview_data(st.session_state.username, config.BACKUPS_DIRECTORY, config.BACKUPS_DIRECTORY,
                                        f"_transcript_started_{st.session_state.start_time_file_names}",
                                        f"_time_started_{st.session_state.start_time_file_names}")
                except:
                    pass

            for code in config.CLOSING_MESSAGES.keys():
                if code in reply:
                    st.session_state.messages.append({"role": "assistant", "content": reply})
                    st.session_state.interview_active = False
                    closing = config.CLOSING_MESSAGES[code]
                    st.markdown(closing)
                    st.session_state.messages.append({"role": "assistant", "content": closing})
                    final_transcript_stored = False
                    while not final_transcript_stored:
                        save_interview_data(st.session_state.username, config.TRANSCRIPTS_DIRECTORY, config.TIMES_DIRECTORY)
                        final_transcript_stored = check_if_interview_completed(config.TRANSCRIPTS_DIRECTORY, st.session_state.username)
                        time.sleep(0.1)

# Admin download interface
if st.session_state.username == "admin":
    st.sidebar.markdown("### 🔐 Admin Downloads")
    for root, _, files in os.walk("data"):
        for file in files:
            if file.endswith(".csv"):
                with open(os.path.join(root, file), "rb") as f:
                    st.sidebar.download_button(
                        label=f"Download {file}",
                        data=f,
                        file_name=file,
                        mime="text/csv"
                    )

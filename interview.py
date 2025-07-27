import streamlit as st
import time
import os
import csv
from utils import (
    check_password,
    check_if_interview_completed,
    save_interview_data,
    append_to_master_csv,
)
import config

# Load API library
if "gpt" in config.MODEL.lower():
    from openai import OpenAI
    api = "openai"
elif "claude" in config.MODEL.lower():
    import anthropic
    api = "anthropic"
else:
    raise ValueError("Model must contain 'gpt' or 'claude'.")

# Page config
st.set_page_config(page_title="Interview", page_icon=config.AVATAR_INTERVIEWER)

# Auth
if config.LOGINS:
    pwd_correct, username = check_password()
    if not pwd_correct:
        st.stop()
    st.session_state.username = username
else:
    st.session_state.username = "testaccount"

# Create folders
os.makedirs("data", exist_ok=True)
for folder in [config.TRANSCRIPTS_DIRECTORY, config.TIMES_DIRECTORY, config.BACKUPS_DIRECTORY]:
    os.makedirs(folder, exist_ok=True)

# Session state setup
st.session_state.setdefault("interview_active", True)
st.session_state.setdefault("messages", [])
if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()
    st.session_state.start_time_file_names = time.strftime("%Y_%m_%d_%H_%M_%S", time.localtime(st.session_state.start_time))

# Exit if already completed
if check_if_interview_completed(config.TIMES_DIRECTORY, st.session_state.username) and not st.session_state.messages:
    st.session_state.interview_active = False
    st.markdown("Interview already completed.")

# Quit button
if st.session_state.interview_active:
    with st.columns([0.85, 0.15])[1]:
        if st.button("Quit", help="End the interview."):
            st.session_state.interview_active = False
            quit_msg = "You have cancelled the interview."
            st.session_state.messages.append({"role": "assistant", "content": quit_msg})
            append_to_master_csv(st.session_state.username, "assistant", quit_msg)
            save_interview_data(st.session_state.username, config.TRANSCRIPTS_DIRECTORY, config.TIMES_DIRECTORY)

# Display chat history
for m in st.session_state.messages[1:]:
    if not any(code in m["content"] for code in config.CLOSING_MESSAGES.keys()):
        with st.chat_message(m["role"], avatar=config.AVATAR_INTERVIEWER if m["role"] == "assistant" else config.AVATAR_RESPONDENT):
            st.markdown(m["content"])

# Load model
api_kwargs = {
    "messages": st.session_state.messages,
    "model": config.MODEL,
    "max_tokens": config.MAX_OUTPUT_TOKENS,
}
if config.TEMPERATURE:
    api_kwargs["temperature"] = config.TEMPERATURE

if api == "openai":
    client = OpenAI(api_key=st.secrets["API_KEY_OPENAI"])
    api_kwargs["stream"] = True
elif api == "anthropic":
    client = anthropic.Anthropic(api_key=st.secrets["API_KEY_ANTHROPIC"])
    api_kwargs["system"] = config.SYSTEM_PROMPT

# First assistant message
if not st.session_state.messages:
    if api == "openai":
        st.session_state.messages.append({"role": "system", "content": config.SYSTEM_PROMPT})
        with st.chat_message("assistant", avatar=config.AVATAR_INTERVIEWER):
            stream = client.chat.completions.create(**api_kwargs)
            first_reply = st.write_stream(stream)
    else:  # Claude
        st.session_state.messages.append({"role": "user", "content": "Hi"})
        with st.chat_message("assistant", avatar=config.AVATAR_INTERVIEWER):
            first_reply = ""
            placeholder = st.empty()
            with client.messages.stream(**api_kwargs) as stream:
                for delta in stream.text_stream:
                    first_reply += delta
                    placeholder.markdown(first_reply + "▌")
            placeholder.markdown(first_reply)

    st.session_state.messages.append({"role": "assistant", "content": first_reply})
    append_to_master_csv(st.session_state.username, "assistant", first_reply)
    save_interview_data(st.session_state.username, config.BACKUPS_DIRECTORY, config.BACKUPS_DIRECTORY,
                        f"_transcript_{st.session_state.start_time_file_names}",
                        f"_time_{st.session_state.start_time_file_names}")

# Chat interaction
if st.session_state.interview_active:
    if user_msg := st.chat_input("Your message here"):
        st.session_state.messages.append({"role": "user", "content": user_msg})
        append_to_master_csv(st.session_state.username, "user", user_msg)
        with st.chat_message("user", avatar=config.AVATAR_RESPONDENT):
            st.markdown(user_msg)

        with st.chat_message("assistant", avatar=config.AVATAR_INTERVIEWER):
            placeholder = st.empty()
            reply = ""
            if api == "openai":
                stream = client.chat.completions.create(**api_kwargs)
                for chunk in stream:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        reply += delta
                        placeholder.markdown(reply + "▌")
            else:  # Claude
                with client.messages.stream(**api_kwargs) as stream:
                    for delta in stream.text_stream:
                        reply += delta
                        placeholder.markdown(reply + "▌")

            placeholder.markdown(reply)
            st.session_state.messages.append({"role": "assistant", "content": reply})
            append_to_master_csv(st.session_state.username, "assistant", reply)

            # Auto-save partial transcript
            save_interview_data(st.session_state.username, config.BACKUPS_DIRECTORY, config.BACKUPS_DIRECTORY,
                                f"_transcript_{st.session_state.start_time_file_names}",
                                f"_time_{st.session_state.start_time_file_names}")

            # Final closing check
            for code in config.CLOSING_MESSAGES.keys():
                if code in reply:
                    st.session_state.interview_active = False
                    closing = config.CLOSING_MESSAGES[code]
                    st.session_state.messages.append({"role": "assistant", "content": closing})
                    st.markdown(closing)
                    append_to_master_csv(st.session_state.username, "assistant", closing)
                    final_saved = False
                    while not final_saved:
                        save_interview_data(st.session_state.username, config.TRANSCRIPTS_DIRECTORY, config.TIMES_DIRECTORY)
                        final_saved = check_if_interview_completed(config.TRANSCRIPTS_DIRECTORY, st.session_state.username)
                        time.sleep(0.1)

# Admin download section
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

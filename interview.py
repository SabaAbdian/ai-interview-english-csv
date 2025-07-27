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
    raise ValueError(
        "Model does not contain 'gpt' or 'claude'; unable to determine API."
    )

# Set page title and icon
st.set_page_config(page_title="Interview", page_icon=config.AVATAR_INTERVIEWER)

# Check if usernames and logins are enabled
if config.LOGINS:
    pwd_correct, username = check_password()
    if not pwd_correct:
        st.stop()
    else:
        st.session_state.username = username
else:
    st.session_state.username = "testaccount"

# Create directories if they do not already exist
os.makedirs("data", exist_ok=True)
if not os.path.exists(config.TRANSCRIPTS_DIRECTORY):
    os.makedirs(config.TRANSCRIPTS_DIRECTORY)
if not os.path.exists(config.TIMES_DIRECTORY):
    os.makedirs(config.TIMES_DIRECTORY)
if not os.path.exists(config.BACKUPS_DIRECTORY):
    os.makedirs(config.BACKUPS_DIRECTORY)

# Define user-specific CSV path
CSV_FILE_PATH = f"data/interview_data_{st.session_state.username}_{time.strftime('%Y_%m_%d_%H_%M_%S')}.csv"

# Function to save interview data to CSV
if not os.path.exists(CSV_FILE_PATH):
    with open(CSV_FILE_PATH, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Timestamp', 'Username', 'Role', 'Message'])

def save_to_csv(question, answer):
    with open(CSV_FILE_PATH, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([time.strftime('%Y-%m-%d %H:%M:%S'), st.session_state.username, question, answer])

# Initialise session state
if "interview_active" not in st.session_state:
    st.session_state.interview_active = True

if "messages" not in st.session_state:
    st.session_state.messages = []

if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()
    st.session_state.start_time_file_names = time.strftime("%Y_%m_%d_%H_%M_%S", time.localtime(st.session_state.start_time))

interview_previously_completed = check_if_interview_completed(config.TIMES_DIRECTORY, st.session_state.username)
if interview_previously_completed and not st.session_state.messages:
    st.session_state.interview_active = False
    st.markdown("Interview already completed.")

col1, col2 = st.columns([0.85, 0.15])
with col2:
    if st.session_state.interview_active and st.button("Quit", help="End the interview."):
        st.session_state.interview_active = False
        quit_message = "You have cancelled the interview."
        st.session_state.messages.append({"role": "assistant", "content": quit_message})
        save_interview_data(st.session_state.username, config.TRANSCRIPTS_DIRECTORY, config.TIMES_DIRECTORY)

for message in st.session_state.messages[1:]:
    avatar = config.AVATAR_INTERVIEWER if message["role"] == "assistant" else config.AVATAR_RESPONDENT
    if not any(code in message["content"] for code in config.CLOSING_MESSAGES.keys()):
        with st.chat_message(message["role"], avatar=avatar):
            st.markdown(message["content"])

# Load API client
if api == "openai":
    client = OpenAI(api_key=st.secrets["API_KEY_OPENAI"])
    api_kwargs = {"stream": True}
elif api == "anthropic":
    client = anthropic.Anthropic(api_key=st.secrets["API_KEY_ANTHROPIC"])
    api_kwargs = {"system": config.SYSTEM_PROMPT}

api_kwargs.update({"messages": st.session_state.messages, "model": config.MODEL, "max_tokens": config.MAX_OUTPUT_TOKENS})
if config.TEMPERATURE is not None:
    api_kwargs["temperature"] = config.TEMPERATURE

if not st.session_state.messages:
    if api == "openai":
        st.session_state.messages.append({"role": "system", "content": config.SYSTEM_PROMPT})
        with st.chat_message("assistant", avatar=config.AVATAR_INTERVIEWER):
            stream = client.chat.completions.create(**api_kwargs)
            message_interviewer = st.write_stream(stream)
    elif api == "anthropic":
        st.session_state.messages.append({"role": "user", "content": "Hi"})
        with st.chat_message("assistant", avatar=config.AVATAR_INTERVIEWER):
            message_placeholder = st.empty()
            message_interviewer = ""
            with client.messages.stream(**api_kwargs) as stream:
                for text_delta in stream.text_stream:
                    if text_delta:
                        message_interviewer += text_delta
                    message_placeholder.markdown(message_interviewer + "▌")
            message_placeholder.markdown(message_interviewer)
    st.session_state.messages.append({"role": "assistant", "content": message_interviewer})
    save_interview_data(st.session_state.username, config.BACKUPS_DIRECTORY, config.BACKUPS_DIRECTORY,
                        f"_transcript_started_{st.session_state.start_time_file_names}",
                        f"_time_started_{st.session_state.start_time_file_names}")

if st.session_state.interview_active:
    if message_respondent := st.chat_input("Your message here"):
        st.session_state.messages.append({"role": "user", "content": message_respondent})
        with st.chat_message("user", avatar=config.AVATAR_RESPONDENT):
            st.markdown(message_respondent)
        save_to_csv("User's message", message_respondent)
        save_interview_data(st.session_state.username, config.TRANSCRIPTS_DIRECTORY, config.TIMES_DIRECTORY)

        with st.chat_message("assistant", avatar=config.AVATAR_INTERVIEWER):
            message_placeholder = st.empty()
            message_interviewer = ""
            if api == "openai":
                stream = client.chat.completions.create(**api_kwargs)
                for message in stream:
                    text_delta = message.choices[0].delta.content
                    if text_delta:
                        message_interviewer += text_delta
                    if len(message_interviewer) > 5:
                        message_placeholder.markdown(message_interviewer + "▌")
                    if any(code in message_interviewer for code in config.CLOSING_MESSAGES.keys()):
                        message_placeholder.empty()
                        break
            elif api == "anthropic":
                with client.messages.stream(**api_kwargs) as stream:
                    for text_delta in stream.text_stream:
                        if text_delta:
                            message_interviewer += text_delta
                        if len(message_interviewer) > 5:
                            message_placeholder.markdown(message_interviewer + "▌")
                        if any(code in message_interviewer for code in config.CLOSING_MESSAGES.keys()):
                            message_placeholder.empty()
                            break
            if not any(code in message_interviewer for code in config.CLOSING_MESSAGES.keys()):
                message_placeholder.markdown(message_interviewer)
                st.session_state.messages.append({"role": "assistant", "content": message_interviewer})
                save_to_csv("Assistant's message", message_interviewer)
                try:
                    save_interview_data(st.session_state.username, config.BACKUPS_DIRECTORY, config.BACKUPS_DIRECTORY,
                                        f"_transcript_started_{st.session_state.start_time_file_names}",
                                        f"_time_started_{st.session_state.start_time_file_names}")
                except:
                    pass
            for code in config.CLOSING_MESSAGES.keys():
                if code in message_interviewer:
                    st.session_state.messages.append({"role": "assistant", "content": message_interviewer})
                    st.session_state.interview_active = False
                    closing_message = config.CLOSING_MESSAGES[code]
                    st.markdown(closing_message)
                    st.session_state.messages.append({"role": "assistant", "content": closing_message})
                    final_transcript_stored = False
                    while not final_transcript_stored:
                        save_interview_data(st.session_state.username, config.TRANSCRIPTS_DIRECTORY, config.TIMES_DIRECTORY)
                        final_transcript_stored = check_if_interview_completed(config.TRANSCRIPTS_DIRECTORY, st.session_state.username)
                        time.sleep(0.1)

# Optional: allow the owner to download CSV files from Streamlit UI
if st.session_state.username == "admin":
    st.sidebar.markdown("### Download all transcripts")
    for root, dirs, files in os.walk("data"):
        for file in files:
            if file.endswith(".csv"):
                with open(os.path.join(root, file), "rb") as f:
                    st.sidebar.download_button(label=f"Download {file}", data=f, file_name=file, mime="text/csv")

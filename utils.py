import streamlit as st
import hmac
import time
import os
import csv


# --- Basic password-based authentication ---
def check_password():
    """Returns 'True' if the user has entered a correct password."""

    def login_form():
        with st.form("Credentials"):
            st.text_input("Username", key="username")
            st.text_input("Password", type="password", key="password")
            st.form_submit_button("Log in", on_click=password_entered)

    def password_entered():
        if st.session_state.username in st.secrets.passwords and hmac.compare_digest(
            st.session_state.password,
            st.secrets.passwords[st.session_state.username],
        ):
            st.session_state.password_correct = True
        else:
            st.session_state.password_correct = False
        del st.session_state.password

    if st.session_state.get("password_correct", False):
        return True, st.session_state.username

    login_form()
    if "password_correct" in st.session_state:
        st.error("User or password incorrect")
    return False, st.session_state.username


# --- Check if interview already completed ---
def check_if_interview_completed(directory, username):
    """Check if interview transcript exists (used to limit to one attempt)."""
    if username != "testaccount":
        try:
            with open(os.path.join(directory, f"{username}.txt"), "r") as _:
                return True
        except FileNotFoundError:
            return False
    else:
        return False


# --- Save interview to .txt, .csv, and time file ---
def save_interview_data(
    username,
    transcripts_directory,
    times_directory,
    csv_directory,
    file_name_addition_transcript="",
    file_name_addition_time=""
):
    """Save all chat messages to .txt and .csv files, and log interview timing."""

    # === Save transcript as .txt ===
    os.makedirs(transcripts_directory, exist_ok=True)
    with open(
        os.path.join(transcripts_directory, f"{username}{file_name_addition_transcript}.txt"),
        "w", encoding="utf-8"
    ) as t:
        for message in st.session_state.messages:
            t.write(f"{message['role']}: {message['content']}\n")

    # === Save transcript as user-specific .csv ===
    os.makedirs(csv_directory, exist_ok=True)
    csv_path = os.path.join(csv_directory, f"{username}_interview.csv")
    with open(csv_path, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["Role", "Content"])
        for message in st.session_state.messages:
            writer.writerow([message["role"], message["content"]])

    # === Save interview time summary ===
    os.makedirs(times_directory, exist_ok=True)
    with open(
        os.path.join(times_directory, f"{username}{file_name_addition_time}.txt"),
        "w", encoding="utf-8"
    ) as d:
        duration = (time.time() - st.session_state.start_time) / 60
        d.write(
            f"Start time (UTC): {time.strftime('%d/%m/%Y %H:%M:%S', time.localtime(st.session_state.start_time))}\n"
            f"Interview duration (minutes): {duration:.2f}"
        )


# --- Append each message to admin master log ---
def append_to_master_csv(username, role, content):
    filename = os.path.join(config.CSV_DIRECTORY, f"{username}_interview.csv")
    file_exists = os.path.isfile(filename)
    
    with open(filename, "a", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        if not file_exists:
            writer.writerow(["timestamp", "username", "role", "message"])
        writer.writerow([datetime.datetime.now().isoformat(), username, role, content])

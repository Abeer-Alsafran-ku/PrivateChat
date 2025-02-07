import streamlit as st
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
import datetime
import sqlite3
import hashlib
import time

# Database setup
def init_db():
    conn = sqlite3.connect('chat_database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (username TEXT PRIMARY KEY, password TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS channels
                 (name TEXT PRIMARY KEY, password TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS channel_members
                 (channel_name TEXT, username TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (channel_name TEXT, username TEXT, content TEXT, 
                  timestamp TEXT, role TEXT)''')
    conn.commit()
    conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Modified authentication
def authenticate():
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    
    if not st.session_state.authenticated:
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Login"):
                conn = sqlite3.connect('chat_database.db')
                c = conn.cursor()
                c.execute("SELECT password FROM users WHERE username=?", (username,))
                result = c.fetchone()
                if result and result[0] == hash_password(password):
                    st.session_state.authenticated = True
                    st.session_state.current_user = username
                    conn.close()
                    return True
                else:
                    st.error("Invalid credentials")
                    conn.close()
                    return False
        with col2:
            if st.button("Register"):
                conn = sqlite3.connect('chat_database.db')
                c = conn.cursor()
                c.execute("INSERT OR IGNORE INTO users VALUES (?, ?)", 
                         (username, hash_password(password)))
                conn.commit()
                conn.close()
                st.success("Registration successful!")
    return st.session_state.authenticated

# Modified channel management
def create_channel():
    channel_name = st.text_input("New Channel Name")
    channel_password = st.text_input("Channel Password", type="password")
    if st.button("Create Channel"):
        conn = sqlite3.connect('chat_database.db')
        c = conn.cursor()
        c.execute("INSERT INTO channels VALUES (?, ?)", 
                 (channel_name, hash_password(channel_password)))
        c.execute("INSERT INTO channel_members VALUES (?, ?)", 
                 (channel_name, st.session_state.current_user))
        conn.commit()
        conn.close()
        st.success(f"Channel {channel_name} created!")

def join_channel():
    channel_name = st.text_input("Channel Name")
    channel_password = st.text_input("Channel Password", type="password", key="join_password")
    if st.button("Join Channel"):
        conn = sqlite3.connect('chat_database.db')
        c = conn.cursor()
        c.execute("SELECT password FROM channels WHERE name=?", (channel_name,))
        result = c.fetchone()
        if result and result[0] == hash_password(channel_password):
            c.execute("INSERT INTO channel_members VALUES (?, ?)", 
                     (channel_name, st.session_state.current_user))
            conn.commit()
            conn.close()
            st.success(f"Joined channel {channel_name}")
        else:
            conn.close()
            st.error("Invalid channel or password")

def get_user_channels():
    conn = sqlite3.connect('chat_database.db')
    c = conn.cursor()
    c.execute("""
        SELECT DISTINCT c.name 
        FROM channels c 
        JOIN channel_members cm ON c.name = cm.channel_name 
        WHERE cm.username = ?
    """, (st.session_state.current_user,))
    channels = [row[0] for row in c.fetchall()]
    conn.close()
    return channels

def save_message(channel, message):
    conn = sqlite3.connect('chat_database.db')
    c = conn.cursor()
    c.execute("INSERT INTO messages VALUES (?, ?, ?, ?, ?)",
             (channel, message['user'], message['content'], 
              message['timestamp'], message['role']))
    conn.commit()
    conn.close()

def get_channel_messages(channel):
    conn = sqlite3.connect('chat_database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM messages WHERE channel_name=? ORDER BY timestamp", (channel,))
    messages = []
    for row in c.fetchall():
        messages.append({
            'role': row[4],
            'user': row[1],
            'content': row[2],
            'timestamp': row[3]
        })
    conn.close()
    return messages

# Add this function to check for new messages
def get_last_message_timestamp(channel):
    conn = sqlite3.connect('chat_database.db')
    c = conn.cursor()
    c.execute("SELECT MAX(timestamp) FROM messages WHERE channel_name=?", (channel,))
    result = c.fetchone()[0]
    conn.close()
    return result or "1970-01-01 00:00:00"

# Add this new function after get_user_channels()
def exit_channel(channel_name):
    conn = sqlite3.connect('chat_database.db')
    c = conn.cursor()
    c.execute("DELETE FROM channel_members WHERE channel_name=? AND username=?", 
             (channel_name, st.session_state.current_user))
    conn.commit()
    conn.close()
    if channel_name in st.session_state.last_update:
        del st.session_state.last_update[channel_name]
    return True

# Modify the main function's channel display section
def main():
    init_db()
    st.title("Private Channels Chat Application")
    
    if not authenticate():
        return

    # Add this to track last update
    if 'last_update' not in st.session_state:
        st.session_state.last_update = {}

    with st.sidebar:
        st.header("Channels")
        tab1, tab2 = st.tabs(["Create Channel", "Join Channel"])
        with tab1:
            create_channel()
        with tab2:
            join_channel()
        
        user_channels = get_user_channels()
        selected_channel = st.selectbox(
            "Select Channel",
            options=user_channels
        )

    if selected_channel:
        col1, col2 = st.columns([6, 1])
        with col1:
            st.subheader(f"Channel: {selected_channel}")
        with col2:
            if st.button("Exit Channel"):
                exit_channel(selected_channel)
                st.rerun()
        
        # Auto-refresh container
        chat_container = st.empty()
        
        while True:
            with chat_container.container():
                # Check for new messages
                last_timestamp = get_last_message_timestamp(selected_channel)
                current_last_update = st.session_state.last_update.get(selected_channel, "1970-01-01 00:00:00")
                
                if last_timestamp > current_last_update:
                    messages = get_channel_messages(selected_channel)
                    for message in messages:
                        with st.chat_message(message["role"]):
                            st.markdown(f"**{message['user']}:** {message['content']}")
                            st.caption(f"Sent at {message['timestamp']}")
                    
                    st.session_state.last_update[selected_channel] = last_timestamp

            # Chat input
            if prompt := st.chat_input("Type your message..."):
                message = {
                    "role": "user",
                    "user": st.session_state.current_user,
                    "content": prompt,
                    "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                save_message(selected_channel, message)
                st.rerun()

            # Add a small delay to prevent excessive database queries
            time.sleep(1)
            st.rerun()

if __name__ == "__main__":
    main()

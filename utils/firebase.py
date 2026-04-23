import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import json

def get_firebase_app():
    if not firebase_admin._apps:
        json_str = st.secrets["firebase"]["json_key"]
        cred_dict = json.loads(json_str)
        cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    return firebase_admin.get_app()

def get_db():
    get_firebase_app()
    return firestore.client()

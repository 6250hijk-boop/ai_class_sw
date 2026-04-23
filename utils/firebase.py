import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import json

def get_firebase_app():
    """Firebase 앱 초기화 (중복 초기화 방지)"""
    if not firebase_admin._apps:
        fb = st.secrets["firebase"]
        cred_dict = {
            "type": fb["type"],
            "project_id": fb["project_id"],
            "private_key_id": fb["private_key_id"],
            "private_key": fb["private_key"].replace("\\n", "\n"),
            "client_email": fb["client_email"],
            "client_id": fb["client_id"],
            "auth_uri": fb["auth_uri"],
            "token_uri": fb["token_uri"],
        }
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    return firebase_admin.get_app()

def get_db():
    """Firestore DB 객체 반환"""
    get_firebase_app()
    return firestore.client()

# auth/routes.py
from __future__ import annotations
from datetime import datetime

from flask import Blueprint, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import or_

from extensions import db
from models import User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

def _get(field: str):
    # Accept both form-data and JSON body
    if request.is_json:
        return (request.json or {}).get(field)
    return request.form.get(field)

def _serialize_user(u: User):
    return {
        "id": u.id,
        "email": u.email,
        "username": u.username,
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "last_login": u.last_login.isoformat() if u.last_login else None,
        "is_admin": u.is_admin,
    }

@auth_bp.post("/register")
def register():
    email = (_get("email") or "").strip().lower()
    username = (_get("username") or "").strip()
    password = _get("password") or ""

    # Basic validation
    if not email or not username or not password:
        return jsonify({"ok": False, "error": "All fields are required"}), 400
    if len(username) < 3:
        return jsonify({"ok": False, "error": "Username must be at least 3 characters"}), 400
    if len(password) < 6:
        return jsonify({"ok": False, "error": "Password must be at least 6 characters"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"ok": False, "error": "Email is already registered"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"ok": False, "error": "Username is already taken"}), 400

    u = User(email=email, username=username)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()

    login_user(u, remember=True)
    return jsonify({"ok": True, "user": _serialize_user(u)})

@auth_bp.post("/login")
def login():
    identifier = (_get("identifier") or "").strip().lower()
    password = _get("password") or ""
    
    if not identifier or not password:
        return jsonify({"ok": False, "error": "Missing identifier or password"}), 400
    
    # Try to find user by email or username
    user = User.query.filter(
        or_(User.email == identifier, User.username == identifier)
    ).first()
    
    if not user or not user.check_password(password):
        return jsonify({"ok": False, "error": "Invalid credentials"}), 401
    
    if not user.is_active:
        return jsonify({"ok": False, "error": "Account disabled"}), 403
    
    # Update last login
    user.last_login = datetime.utcnow()
    db.session.commit()
    
    # Log the user in with Flask-Login
    login_user(user, remember=True)  # Add remember=True for persistent session
    
    return jsonify({
        "ok": True,
        "user": _serialize_user(user),
        "message": "Login successful"
    }), 200


@auth_bp.post("/logout")
@login_required
def logout():
    """Log out the current user"""
    logout_user()
    return jsonify({
        "ok": True,
        "message": "Logged out successfully"
    }), 200


@auth_bp.get("/me")
def get_current_user():
    """Get current logged-in user info"""
    if current_user.is_authenticated:
        return jsonify({
            "ok": True,
            "user": _serialize_user(current_user)
        }), 200
    else:
        return jsonify({
            "ok": False,
            "error": "Not authenticated"
        }), 401

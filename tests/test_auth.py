"""Tests for authentication endpoints (POST /api/auth/login, /api/auth/register)."""

import db


class TestLogin:
    def test_login_default_admin(self, client):
        resp = client.post("/api/auth/login", json={
            "username": "admin",
            "password": "admin123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "admin"
        assert data["role"] == "admin"
        assert "password_hash" not in data

    def test_login_wrong_password(self, client):
        resp = client.post("/api/auth/login", json={
            "username": "admin",
            "password": "wrong",
        })
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client):
        resp = client.post("/api/auth/login", json={
            "username": "ghost",
            "password": "anything",
        })
        assert resp.status_code == 401


class TestRegister:
    def test_register_new_user(self, client):
        resp = client.post("/api/auth/register", json={
            "username": "newuser",
            "password": "securepass",
            "name": "New User",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "newuser"
        assert data["role"] == "user"

    def test_register_duplicate_username(self, client):
        resp = client.post("/api/auth/register", json={
            "username": "admin",
            "password": "whatever",
            "name": "Duplicate",
        })
        assert resp.status_code == 409

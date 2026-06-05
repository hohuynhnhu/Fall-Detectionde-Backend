"""
tests/test_contacts.py — Test CRUD liên hệ khẩn cấp.

Endpoints:
    GET    /contacts
    POST   /contacts
    DELETE /contacts/{id}
"""
from __future__ import annotations


class TestContacts:
    def test_list_empty(self, client):
        r = client.get("/contacts")
        assert r.status_code == 200
        assert r.json() == []

    def test_create_basic(self, client):
        """Tạo liên hệ với đầy đủ thông tin."""
        r = client.post("/contacts", json={
            "name":     "Nguyễn Văn B",
            "phone":    "0912345678",
            "relation": "Con trai",
        })
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "Nguyễn Văn B"
        assert data["phone"] == "0912345678"
        assert data["relation"] == "Con trai"
        assert data["is_active"] is True
        assert data["id"] == 1

    def test_create_without_relation(self, client):
        """relation là optional."""
        r = client.post("/contacts", json={
            "name":  "Trần Thị C",
            "phone": "0900000001",
        })
        assert r.status_code == 201
        assert r.json()["relation"] is None

    def test_create_multiple(self, client):
        """Tạo nhiều liên hệ — id tăng dần."""
        for i in range(3):
            client.post("/contacts", json={
                "name":  f"Người {i}",
                "phone": f"090000000{i}",
            })
        contacts = client.get("/contacts").json()
        assert len(contacts) == 3
        assert [c["id"] for c in contacts] == [1, 2, 3]

    def test_delete_existing(self, client):
        """Xóa liên hệ tồn tại."""
        client.post("/contacts", json={"name": "Test", "phone": "0900000000"})
        r = client.delete("/contacts/1")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert client.get("/contacts").json() == []

    def test_delete_not_found(self, client):
        """Xóa liên hệ không tồn tại → 404."""
        r = client.delete("/contacts/999")
        assert r.status_code == 404

    def test_delete_one_keeps_others(self, client):
        """Xóa 1 liên hệ, các liên hệ khác vẫn còn."""
        client.post("/contacts", json={"name": "A", "phone": "0901111111"})
        client.post("/contacts", json={"name": "B", "phone": "0902222222"})
        client.post("/contacts", json={"name": "C", "phone": "0903333333"})

        client.delete("/contacts/2")  # xóa B

        contacts = client.get("/contacts").json()
        assert len(contacts) == 2
        names = [c["name"] for c in contacts]
        assert "A" in names
        assert "C" in names
        assert "B" not in names

    def test_all_contacts_active_by_default(self, client):
        """Liên hệ mới tạo luôn is_active=True."""
        for i in range(3):
            client.post("/contacts", json={"name": f"P{i}", "phone": f"09{i:08d}"})
        contacts = client.get("/contacts").json()
        assert all(c["is_active"] for c in contacts)
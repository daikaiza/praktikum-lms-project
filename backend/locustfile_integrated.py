import random
from locust import HttpUser, task, between

AUTH_TOKEN = "eyJhbGciOiJIUzI1NiIsImtpZCI6InFzNGg5M0tidXdvaHN0N2ciLCJ0eXAiOiJKV1QifQ.eyJpc3MiOiJodHRwczovL3J2bWhob3FoZmhkdGNybm5haWd4LnN1cGFiYXNlLmNvL2F1dGgvdjEiLCJzdWIiOiI5YmM2MTdhZi0wZGQ2LTQ4MmItYTMxYy1mY2JjNTkxMDBlYWQiLCJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzYzMzg5NDQyLCJpYXQiOjE3NjMzODU4NDIsImVtYWlsIjoidG9nZXBpQGl0Yi5hYy5pZCIsInBob25lIjoiIiwiYXBwX21ldGFkYXRhIjp7InByb3ZpZGVyIjoiZW1haWwiLCJwcm92aWRlcnMiOlsiZW1haWwiXX0sInVzZXJfbWV0YWRhdGEiOnsiZW1haWxfdmVyaWZpZWQiOnRydWUsIm5hbWUiOiJUb2dlcGkiLCJuaW0iOiIxODEyNjAwMiIsInJvbGUiOiJzdHVkZW50In0sInJvbGUiOiJhdXRoZW50aWNhdGVkIiwiYWFsIjoiYWFsMSIsImFtciI6W3sibWV0aG9kIjoicGFzc3dvcmQiLCJ0aW1lc3RhbXAiOjE3NjMzODU4NDJ9XSwic2Vzc2lvbl9pZCI6ImVlNzc2YjQ5LThiZmYtNDZmMy1iNGFhLTc0NzljZTFlODE5YiIsImlzX2Fub255bW91cyI6ZmFsc2V9.Cc5YyYKcEbTTk_poZlketxGSSBFn7hThsdXVZVd7ih4"
VALID_MODULE_ID = 1 

HOST_URL = "http://localhost:5001"

class StudentUser(HttpUser):
    wait_time = between(1, 5)
    host = HOST_URL

    def on_start(self):
        """Dijalankan sekali per pengguna virtual saat 'login'"""
        self.client.headers = {
            "Authorization": f"Bearer {AUTH_TOKEN}",
            "Content-Type": "application/json"
        }
        # Tes login (sebenarnya hanya validasi token)
        self.client.get("/api/my-courses")

    @task(3)
    def view_courses_and_modules(self):
        """Simulasi mahasiswa melihat-lihat materi"""
        # 1. Lihat semua mata kuliah
        self.client.get("/api/my-courses", name="/api/my-courses")
        
        # 2. Lihat modul (contoh untuk course_id=1)
        self.client.get("/api/courses/1/modules", name="/api/courses/[id]/modules")

    @task(1)
    def start_lab_session(self):
        """
        Tes Kritis (Stress Test): 
        Mensimulasikan mahasiswa mengklik 'Launch Lab'.
        Ini akan memicu: Backend -> Orchestrator -> Docker container run
        """
        payload = {
            "module_id": VALID_MODULE_ID
        }
        self.client.post("/api/labs/start", 
                         json=payload, 
                         name="/api/labs/start")

    @task(2)
    def view_assignments(self):
        """Simulasi mahasiswa melihat halaman tugas"""
        # Asumsi user_id didapat dari token, jadi endpointnya /my-deadlines
        self.client.get("/api/my-deadlines", name="/api/my-deadlines")
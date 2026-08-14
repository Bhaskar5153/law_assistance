# Law Assistance

Run the backend from the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
cd backend
python -m uvicorn app.main:app --reload --port 8083
```

In a second terminal, run the frontend:

```powershell
cd frontend
npm run dev
```

The Vite development server proxies `/api` requests to the backend on port 8083.

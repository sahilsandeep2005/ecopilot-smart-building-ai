$ErrorActionPreference = "Stop"
& .\.venv\Scripts\Activate.ps1
python -m streamlit run dashboard/app.py

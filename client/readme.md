venv\Scripts\activate

pip install numpy opencv-python pillow
python -m PyInstaller --onefile --noconsole --collect-all numpy --collect-all cv2 --hidden-import=numpy --hidden-import=cv2 --name kapcher_client app.py   




import customtkinter as ctk
import tkinter as tk
import mss
import cv2
import numpy as np
import threading
import time
import random
import keyboard
import json
import os

# --- ส่วนของ Area Selector (กล่องสีชมพูโปร่งแสง) ---
class AreaSelector:
    def __init__(self, callback):
        self.callback = callback
        self.root = tk.Toplevel()
        self.root.attributes("-alpha", 0.3)
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)
        self.root.state('zoomed')
        self.root.config(cursor="cross")

        self.canvas = tk.Canvas(self.root, cursor="cross", bg="grey")
        self.canvas.pack(fill="both", expand=True)

        self.start_x = None
        self.start_y = None
        self.rect = None

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.root.bind("<Escape>", lambda e: self.root.destroy())

    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, 1, 1, outline="red", width=3)

    def on_drag(self, event):
        self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def on_release(self, event):
        end_x, end_y = event.x, event.y
        # คำนวณขอบเขต (Left, Top, Width, Height)
        left = min(self.start_x, end_x)
        top = min(self.start_y, end_y)
        width = abs(self.start_x - end_x)
        height = abs(self.start_y - end_y)
        self.callback(left, top, width, height)
        self.root.destroy()

# --- ส่วนของโปรแกรมหลัก ---
class MacroApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("AI Object Macro - Study Tool")
        self.geometry("450x650")
        ctk.set_appearance_mode("dark")
        
        # ตัวแปรระบบ
        self.running = False
        self.scan_area = {"left": 0, "top": 0, "width": 100, "height": 100}
        self.last_action_time = [0, 0, 0] # เก็บเวลาล่าสุดที่กดของวัตถุ 1, 2, 3

        # UI Layout
        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        # หัวข้อ
        self.label = ctk.CTkLabel(self, text="Macro Detection Setup", font=("Arial", 20, "bold"))
        self.label.pack(pady=10)

        # ปุ่มเลือกพื้นที่
        self.area_btn = ctk.CTkButton(self, text="Select Detection Area (ESC to cancel)", fg_color="#ff007a", command=self.open_selector)
        self.area_btn.pack(pady=5)
        self.area_label = ctk.CTkLabel(self, text="Area: Not set", text_color="gray")
        self.area_label.pack()

        # ส่วนตั้งค่า Object 1-3
        self.create_obj_frame(1, "Object 1 (10s Delay)", "10", "F1")
        self.create_obj_frame(2, "Object 2 (30s Delay)", "30", "F2")
        self.create_obj_frame(3, "Object 3 (60s Delay)", "60", "F3")

        # ปุ่มเริ่ม/หยุด
        self.start_btn = ctk.CTkButton(self, text="START MACRO", fg_color="green", height=50, font=("Arial", 16, "bold"), command=self.toggle_macro)
        self.start_btn.pack(pady=20, padx=20, fill="x")

        self.status_label = ctk.CTkLabel(self, text="Status: Idle", text_color="yellow")
        self.status_label.pack()

    def create_obj_frame(self, num, title, delay, key):
        frame = ctk.CTkFrame(self)
        frame.pack(pady=5, padx=20, fill="x")
        
        ctk.CTkLabel(frame, text=title, font=("Arial", 12, "bold")).grid(row=0, column=0, columnspan=2, padx=10, pady=5)
        
        # ช่องใส่ชื่อไฟล์ภาพ
        ctk.CTkLabel(frame, text="Image File:").grid(row=1, column=0, padx=5)
        setattr(self, f"img_path_{num}", ctk.CTkEntry(frame, placeholder_text="obj1.png", width=120))
        getattr(self, f"img_path_{num}").grid(row=1, column=1, padx=5, pady=2)

        # ช่องใส่ปุ่มที่จะกด
        ctk.CTkLabel(frame, text="Press Key:").grid(row=2, column=0, padx=5)
        setattr(self, f"key_{num}", ctk.CTkEntry(frame, width=120))
        getattr(self, f"key_{num}").insert(0, key)
        getattr(self, f"key_{num}").grid(row=2, column=1, padx=5, pady=2)

    def open_selector(self):
        AreaSelector(self.set_area)

    def set_area(self, l, t, w, h):
        self.scan_area = {"left": l, "top": t, "width": w, "height": h}
        self.area_label.configure(text=f"Area: X={l}, Y={t}, W={w}, H={h}", text_color="#00daff")

    def toggle_macro(self):
        if not self.running:
            self.running = True
            self.start_btn.configure(text="STOP MACRO (CTRL+Q)", fg_color="red")
            self.status_label.configure(text="Status: RUNNING...", text_color="#00FF00")
            threading.Thread(target=self.macro_loop, daemon=True).start()
        else:
            self.stop_macro()

    def stop_macro(self):
        self.running = False
        self.start_btn.configure(text="START MACRO", fg_color="green")
        self.status_label.configure(text="Status: Idle", text_color="yellow")

    def macro_loop(self):
        # โหลดภาพ Template
        templates = []
        delays = [10, 30, 60]
        
        # ตรวจสอบว่าไฟล์ภาพมีจริงไหม
        for i in range(1, 4):
            path = getattr(self, f"img_path_{i}").get()
            if os.path.exists(path):
                img = cv2.imread(path, 0) # โหลดแบบ Grayscale
                templates.append(img)
            else:
                templates.append(None)

        with mss.mss() as sct:
            while self.running:
                # ตรวจจับปุ่มหยุดฉุกเฉิน
                if keyboard.is_pressed('ctrl+q'):
                    self.after(0, self.stop_macro)
                    break

                # จับภาพหน้าจอเฉพาะส่วนที่เลือก
                screenshot = np.array(sct.grab(self.scan_area))
                gray_screen = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2GRAY)

                now = time.time()

                for i, template in enumerate(templates):
                    if template is None: continue
                    
                    obj_num = i + 1
                    # เช็คคูลดาวน์ก่อนตรวจจับ
                    if now - self.last_action_time[i] >= delays[i]:
                        
                        # ใช้ OpenCV Match Template
                        res = cv2.matchTemplate(gray_screen, template, cv2.TM_CCOEFF_NORMED)
                        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

                        if max_val > 0.8: # ความแม่นยำ 80%
                            key_to_press = getattr(self, f"key_{obj_num}").get()
                            
                            # สุ่มความคลาดเคลื่อน (Jitter) 0.5 - 0.7 ตามโจทย์
                            jitter = random.uniform(0.5, 0.7)
                            print(f"Found Obj {obj_num}! Waiting {jitter:.2f}s before pressing {key_to_press}")
                            
                            time.sleep(jitter)
                            keyboard.press_and_release(key_to_press)
                            
                            self.last_action_time[i] = time.time()

                time.sleep(0.1) # พัก CPU

    # ระบบ Save/Load Settings (เพื่อไม่ต้องกรอกใหม่ทุกครั้ง)
    def save_settings(self):
        data = {
            "area": self.scan_area,
            "img1": self.img_path_1.get(),
            "img2": self.img_path_2.get(),
            "img3": self.img_path_3.get()
        }
        with open("macro_config.json", "w") as f:
            json.dump(data, f)

    def load_settings(self):
        if os.path.exists("macro_config.json"):
            with open("macro_config.json", "r") as f:
                data = json.load(f)
                self.set_area(data["area"]["left"], data["area"]["top"], data["area"]["width"], data["area"]["height"])
                self.img_path_1.insert(0, data.get("img1", ""))
                self.img_path_2.insert(0, data.get("img2", ""))
                self.img_path_3.insert(0, data.get("img3", ""))

if __name__ == "__main__":
    app = MacroApp()
    app.mainloop()
import ttkbootstrap as tb
import tkinter as tk
from tkinter import ttk

def test():
    root = tb.Window(themename="cosmo")
    root.title("Test")
    root.geometry("300x200")
    
    label = tb.Label(root, text="Hello TTKBootstrap")
    label.pack(pady=20)
    
    btn = tb.Button(root, text="Click Me", bootstyle="primary")
    btn.pack(pady=10)
    
    print("Window created")
    root.after(1000, lambda: print("Running..."))
    root.mainloop()

if __name__ == "__main__":
    try:
        test()
    except Exception as e:
        print(f"Error: {e}")

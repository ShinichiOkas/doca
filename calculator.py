#!/usr/bin/env python

import tkinter as tk
from math import sqrt, sin, cos, tan, pi

class Calculator:
    def __init__(self, root):
        self.root = root
        self.root.title('Scientific Calculator')
        self.display = tk.Entry(root, width=35, borderwidth=5)
        self.display.grid(row=0, column=0, columnspan=4, padx=10, pady=10)

        # Define buttons
        buttons = [
            ('7', 1, 0), ('8', 1, 1), ('9', 1, 2), ('/', 1, 3),
            ('4', 2, 0), ('5', 2, 1), ('6', 2, 2), ('*', 2, 3),
            ('1', 3, 0), ('2', 3, 1), ('3', 3, 2), ('-', 3, 3),
            ('0', 4, 0), ('.', 4, 1), ('=', 4, 2), ('+', 4, 3),
            ('sqrt', 5, 0), ('^', 5, 1), ('sin', 5, 2), ('cos', 5, 3)
        ]

        for (text, row, col) in buttons:
            button = tk.Button(root, text=text, width=10, height=4,
                              command=lambda t=text: self.on_button_click(t))
            button.grid(row=row, column=col)

    def on_button_click(self, value):
        if value == '=':
            try:
                result = eval(self.display.get())
                self.display.delete(0, tk.END)
                self.display.insert(tk.END, str(result))
            except Exception as e:
                self.display.delete(0, tk.END)
                self.display.insert(tk.END, 'Error')
        elif value in ('sqrt', '^', 'sin', 'cos'):
            try:
                result = eval(f'{value}({self.display.get()})')
                self.display.delete(0, tk.END)
                self.display.insert(tk.END, str(result))
            except Exception as e:
                self.display.delete(0, tk.END)
                self.display.insert(tk.END, 'Error')
        else:
            self.display.insert(tk.END, value)

import os

if __name__ == '__main__':
    root = tk.Tk()
    calc = Calculator(root)
    if os.getenv('TEST_MODE') == '1':
        root.after(1000, root.destroy)
    root.mainloop()
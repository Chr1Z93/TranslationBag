import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os


class App:
    def __init__(self):
        """Initializes the UI by creating the elements"""
        self.cfg = {}
        self.root = tk.Tk()
        self.root.protocol("WM_DELETE_WINDOW", self.close_app)

        # definition of input fields, labels and expected type
        self.fields = [
            ("Max Filesize Byte", "img_max_byte", int),
            ("Image Width", "img_w", int),
            ("Image Height", "img_h", int),
            ("Cloud Name", "cloud_name", str),
            ("API Key", "api_key", str),
            ("API Secret", "api_secret", str),
            ("Locale", "locale", str),
            ("Max Sheet Count", "max_sheet_count", int),
        ]

        self.entries = {}

        # create input fields
        for i, (label_text, var_name, _) in enumerate(self.fields):
            ttk.Label(self.root, text=label_text).grid(
                row=i, column=0, padx=10, pady=5, sticky=tk.E
            )
            entry = ttk.Entry(self.root, justify="right")
            entry.grid(row=i, column=1, padx=10, pady=5)
            self.entries[var_name] = entry

        # create source folder field and browse button
        ttk.Label(self.root, text="Source Folder").grid(
            row=len(self.fields), column=0, padx=10, pady=5, sticky=tk.E
        )
        self.source_folder_entry = ttk.Entry(self.root)
        self.source_folder_entry.grid(row=len(self.fields), column=1, padx=10, pady=5)
        self.browse_button = ttk.Button(
            self.root, text="Browse", command=self.browse_source_folder
        )
        self.browse_button.grid(row=len(self.fields), column=2, padx=10, pady=5)

        # checkbox for keeping the temp folder
        self.keep_temp_folder_var = tk.BooleanVar()

        # sliders
        self.count_per_sheet_slider, self.count_per_sheet_label = self.create_slider(
            len(self.fields) + 2,
            "Image Count per Sheet",
            10,
            70,
            self.update_label,
            "10",
            10,
        )

        self.quality_slider, self.quality_label = self.create_slider(
            len(self.fields) + 3, "Image Quality", 1, 100, self.update_label, "90"
        )

        # submit button
        self.submit_button = ttk.Button(self.root, text="Submit", command=self.submit)
        self.submit_button.grid(row=len(self.fields) + 5, columnspan=3, pady=10)

        self.load_settings()
        self.start_app()

    def create_slider(self, row, text, from_, to, command, label_text, step=1):
        """Helper function to create sliders with a value label"""
        ttk.Label(self.root, text=text).grid(
            row=row, column=0, padx=10, pady=5, sticky=tk.E
        )
        slider = ttk.Scale(
            self.root,
            from_=from_,
            to=to,
            orient=tk.HORIZONTAL,
            length=135,
        )
        slider.grid(row=row, column=1, padx=10, pady=5)
        label = ttk.Label(self.root, text=label_text)
        label.grid(row=row, column=2, padx=10, pady=5)
        slider["command"] = lambda value: command(label, value, step)
        return slider, label

    def close_app(self):
        """Run when the window is closed"""
        exit()

    def load_settings(self):
        """Loads settings from the config file"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(script_dir)
        config_path = os.path.join(parent_dir, "config.json")

        if not os.path.exists(config_path):
            return

        with open(config_path, "r") as f:
            self.cfg.update(json.load(f))

        for _, var_name, expected_type in self.fields:
            value = self.cfg.get(var_name, "")

            # convert the value back to string for display in the entry widget
            if expected_type != str and value != "":
                value = str(value)

            self.entries[var_name].insert(0, value)

        # load settings for source folder
        self.source_folder_entry.insert(0, self.cfg.get("source_folder", ""))

        # load settings for sliders and labels
        self.count_per_sheet_slider.set(self.cfg.get("img_count_per_sheet", 30))
        self.update_label(
            self.count_per_sheet_label, self.cfg.get("img_count_per_sheet", 30), 10
        )
        self.quality_slider.set(self.cfg.get("img_quality", 90))
        self.update_label(self.quality_label, self.cfg.get("img_quality", 90))

    def submit(self):
        """Reads the form and saves settings to config file before continuing"""
        try:
            # get values from input fields
            for field_name, var_name, expected_type in self.fields:
                value = self.entries[var_name].get()
                if not value:
                    raise ValueError(f"Field '{field_name}' is empty.")

                try:
                    if expected_type == int:
                        self.cfg[var_name] = int(value)
                    else:
                        self.cfg[var_name] = value
                except ValueError:
                    raise ValueError(
                        f"Invalid input for '{field_name}'. Please enter a valid {expected_type.__name__}."
                    )

            # get values from sliders
            self.cfg["img_quality"] = int(self.quality_slider.get())
            self.cfg["img_count_per_sheet"] = (
                round(self.count_per_sheet_slider.get() / 10) * 10
            )

            # save settings
            with open("config.json", "w") as f:
                json.dump(self.cfg, f, indent=4)

            # quit the GUI and continue with the main script
            self.root.quit()

        except ValueError as e:
            messagebox.showerror("Invalid input", str(e))

    def browse_source_folder(self):
        """Helper function for the browse button of the source-folder field"""
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.source_folder_entry.delete(0, tk.END)
            self.source_folder_entry.insert(0, folder_selected)

    def update_label(self, label, value, step=1):
        """Helper function to update the label of a slider to its value"""
        rounded_value = round(float(value) / step) * step
        label.config(text=str(int(rounded_value)))

    def start_app(self):
        """Create a window that fits all elements in the center of screen"""
        self.root.update()
        w_width = self.root.winfo_width()
        w_height = self.root.winfo_height()
        s_width = self.root.winfo_screenwidth()
        s_height = self.root.winfo_screenheight()
        x = int((s_width / 2) - (w_width / 2))
        y = int((s_height / 2) - (w_height / 2))

        self.root.geometry(f"{w_width}x{w_height}+{x}+{y}")
        self.root.resizable(False, False)
        self.root.title("Translation Bag")
        self.root.mainloop()

    def get_values(self):
        """Helper function to get the config values"""
        return self.cfg

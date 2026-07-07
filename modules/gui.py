import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
import sys


class App:
    def __init__(self):
        """Initializes the UI by creating the elements"""

        # Define absolute path for config file
        script_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(script_dir)
        self.config_path = os.path.join(parent_dir, "config.json")

        self.DEFAULTS = {
            "img_max_kb": 20_480,
            "cloud_name": "-",
            "api_key": "-",
            "api_secret": "-",
            "locale": "en",
            "max_sheet_count": 999,
            "output_folder": self.generate_default_output_path(),
            "source_folder": "",
            "upload": False,
            "img_count_per_sheet": 30,
            "img_quality": 90,
            "img_contrast": 100,
        }

        self.root = tk.Tk()
        self.root.protocol("WM_DELETE_WINDOW", self.close_app)

        # definition of input fields, labels and expected type
        self.fields = [
            ("Max Filesize per Sheet [KB]", "img_max_kb", int),
            ("Cloud Name", "cloud_name", str),
            ("API Key", "api_key", str),
            ("API Secret", "api_secret", str),
            ("Locale", "locale", str),
            ("Max Sheet Count", "max_sheet_count", int),
        ]
        field_count = len(self.fields)

        self.entries = {}

        # create input fields
        for i, (label_text, var_name, _) in enumerate(self.fields):
            ttk.Label(text=label_text).grid(
                row=i, column=0, padx=10, pady=5, sticky=tk.E
            )
            entry = ttk.Entry(justify="right")
            entry.grid(row=i, column=1, padx=10, pady=5)
            self.entries[var_name] = entry

        # create source folder field and browse button
        ttk.Label(text="Source Folder").grid(
            row=field_count, column=0, padx=10, pady=5, sticky=tk.E
        )
        self.source_folder_entry = ttk.Entry(self.root)
        self.source_folder_entry.grid(row=field_count, column=1, padx=10, pady=5)
        self.browse_source_button = ttk.Button(
            text="Browse", command=self.browse_source_folder
        )
        self.browse_source_button.grid(row=field_count, column=2, padx=10, pady=5)

        ttk.Label(text="Bag Output Folder").grid(
            row=field_count + 1, column=0, padx=10, pady=5, sticky=tk.E
        )
        self.output_folder_entry = ttk.Entry(self.root)
        self.output_folder_entry.grid(row=field_count + 1, column=1, padx=10, pady=5)
        self.browse_output_button = ttk.Button(
            text="Browse", command=self.browse_output_folder
        )
        self.browse_output_button.grid(row=field_count + 1, column=2, padx=10, pady=5)

        # Sliders
        self.count_per_sheet_slider, self.count_per_sheet_label = self.create_slider(
            field_count + 2,
            "Image Count per Sheet",
            10,
            70,
            self.update_label,
            "10",
            10,
        )

        self.quality_slider, self.quality_label = self.create_slider(
            field_count + 3,
            "Image Quality [%]",
            1,
            100,
            self.update_label,
            "90",
        )

        self.contrast_slider, self.contrast_label = self.create_slider(
            field_count + 4,
            "Image Contrast [%]",
            1,
            200,
            self.update_label,
            "100",
        )

        self.contrast_reset_button = ttk.Button(
            text="Reset Contrast", command=self.reset_contrast
        )
        self.contrast_reset_button.grid(row=field_count + 5, column=2, padx=10, pady=5)

        # Row + 5: Upload Sheets
        ttk.Label(text="Upload Sheets to Cloud").grid(
            row=field_count + 5, column=0, padx=10, sticky=tk.E
        )
        self.upload_var = tk.BooleanVar(value=False)
        self.upload = tk.Checkbutton(variable=self.upload_var).grid(
            row=field_count + 5, column=1, padx=10, sticky=tk.W
        )

        # Row + 6: Submit button
        self.submit_button = ttk.Button(text="Submit", command=self.submit)
        self.submit_button.grid(row=field_count + 6, columnspan=3, pady=10)

        # Start with a copy of the default settings
        self.cfg = self.DEFAULTS.copy()
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

        # make sure the slider position matches the initial value
        slider.set(label_text)

        label = ttk.Label(self.root, text=label_text)
        label.grid(row=row, column=2, padx=10, pady=5)
        slider["command"] = lambda value: command(label, value, step)
        return slider, label

    def close_app(self):
        """Run when the window is closed"""
        self.root.destroy()
        sys.exit()

    def load_settings(self):
        """Loads settings from the config file"""

        # Attempt to read and update self.cfg if the file actually exists
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    self.cfg.update(json.load(f))
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading config file, using defaults: {e}")

        for _, var_name, expected_type in self.fields:
            value = self.cfg.get(var_name, "")

            # convert the value back to string for display in the entry widget
            if expected_type != str and value != "":
                value = str(value)

            self.entries[var_name].insert(0, value)

        # load settings for folders
        self.source_folder_entry.insert(0, self.cfg["source_folder"])
        self.output_folder_entry.insert(0, self.cfg["output_folder"])

        # load settings for checkboxes
        self.upload_var.set(self.cfg["upload"])

        # load settings for sliders and labels
        self.count_per_sheet_slider.set(self.cfg["img_count_per_sheet"])
        self.update_label(self.count_per_sheet_label, self.cfg["img_count_per_sheet"])

        self.quality_slider.set(self.cfg["img_quality"])
        self.update_label(self.quality_label, self.cfg["img_quality"])

        self.contrast_slider.set(self.cfg["img_contrast"])
        self.update_label(self.contrast_label, self.cfg["img_contrast"])

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

            # get paths
            self.cfg["source_folder"] = self.source_folder_entry.get().strip()
            if not os.path.exists(self.cfg["source_folder"]) or not os.path.isdir(
                self.cfg["source_folder"]
            ):
                raise ValueError("Source folder does not exist.")
            self.cfg["output_folder"] = self.output_folder_entry.get().strip()
            if not os.path.exists(self.cfg["output_folder"]) or not os.path.isdir(
                self.cfg["output_folder"]
            ):
                raise ValueError("Output folder does not exist.")

            # get values from sliders
            self.cfg["img_quality"] = int(self.quality_slider.get())
            self.cfg["img_count_per_sheet"] = (
                round(self.count_per_sheet_slider.get() / 10) * 10
            )
            self.cfg["img_contrast"] = int(self.contrast_slider.get())

            # get values from checkboxes
            self.cfg["upload"] = bool(self.upload_var.get())

            # save settings
            with open(self.config_path, "w") as f:
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

    def browse_output_folder(self):
        """Helper function for the browse button of the bag output folder field"""
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.output_folder_entry.delete(0, tk.END)
            self.output_folder_entry.insert(0, folder_selected)

    def reset_contrast(self):
        """Helper function for the reset contrast button"""
        self.cfg["img_contrast"] = 100
        self.contrast_slider.set(100)
        self.update_label(self.contrast_label, 100)

    def generate_default_output_path(self):
        if sys.platform == "darwin":  # macOS
            base_folder = os.path.join(
                os.path.expanduser("~"),
                "Library",
            )
        elif sys.platform == "linux":  # linux
            base_folder = os.path.join(os.path.expanduser("~"), ".local", "share")
        else:  # windows
            base_folder = os.path.join(
                os.environ["USERPROFILE"],
                "Documents",
                "My Games",
            )
        return os.path.join(
            f"{base_folder}",
            "Tabletop Simulator",
            "Saves",
            "Saved Objects",
        ).replace("\\", "/")

    def set_default_output_folder(self):
        """Helper function to set output folder as default ('TTS/Saves/Saved Objects' folder)"""
        self.output_folder_entry.delete(0, tk.END)
        self.output_folder_entry.insert(0, self.generate_default_output_path())

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

"""Standard ScrolledText API with the application's themed scrollbar."""
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText as TkScrolledText


class ScrolledText(TkScrolledText):
    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        self.vbar.destroy()
        self.vbar = ttk.Scrollbar(self.frame, orient='vertical', command=self.yview)
        self.vbar.pack(side='right', fill='y', before=self._w)
        self.configure(yscrollcommand=self.vbar.set)

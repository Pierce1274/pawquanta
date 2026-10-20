"""Short, dependency-free startup animation for the desktop wallet."""
import os
import time
import tkinter as tk


class LaunchSplash:
    def __init__(self, owner, version, duration=1.8):
        self.owner = owner
        self.duration = duration
        self.started = time.monotonic()
        self.closed = False
        self.timer = None
        self.window = tk.Toplevel(owner)
        self.window.title('Pawquanta - Starting')
        self.window.resizable(False, False)
        self.window.configure(bg='#080d17')
        width, height = 680, 430
        x = max(0, (owner.winfo_screenwidth() - width) // 2)
        y = max(0, (owner.winfo_screenheight() - height) // 2)
        self.window.geometry(f'{width}x{height}+{x}+{y}')
        self.window.protocol('WM_DELETE_WINDOW', self.finish)
        self.window.bind('<Escape>', lambda event: self.finish())
        self.canvas = tk.Canvas(self.window, width=width, height=height,
                                background='#080d17', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        c = self.canvas
        for row in range(0, height, 4):
            shade = int(13 + 8 * (1 - abs(row - 210) / 220))
            c.create_rectangle(0, row, width, row + 4,
                               fill=f'#08{shade:02x}{shade+12:02x}', outline='')
        for col in range(24, width, 36):
            c.create_line(col, 0, col, height, fill='#101e2c')
        for row in range(12, height, 36):
            c.create_line(0, row, width, row, fill='#101e2c')
        c.create_text(28, 27, text='P Q  /  N E T W O R K', anchor='w',
                      fill='#6c899d', font=('Segoe UI', 9))
        c.create_text(650, 27, text='WALLET + MINER', anchor='e',
                      fill='#6c899d', font=('Segoe UI', 9))
        self.orbits = []
        for radius, color, extent in ((71, '#48e2cf', 205), (85, '#517dde', 125), (96, '#203c54', 280)):
            self.orbits.append(c.create_arc(340-radius, 155-radius, 340+radius, 155+radius,
                                           style='arc', outline=color, width=2, extent=extent))
        # Paw emblem: simple geometry stays sharp at desktop scale.
        c.create_oval(309, 146, 371, 191, fill='#6cf3db', outline='')
        for dx, dy, radius in ((-29, -10, 11), (-11, -26, 12), (12, -26, 12), (30, -10, 11)):
            c.create_oval(340+dx-radius, 143+dy-radius, 340+dx+radius, 143+dy+radius,
                          fill='#6cf3db', outline='')
        c.create_text(340, 284, text='PAWQUANTA', fill='#f0f6ff', font=('Segoe UI', 31, 'bold'))
        c.create_text(340, 320, text='Your wallet. Your work. Your network.',
                      fill='#92a9bc', font=('Segoe UI', 12))
        c.create_rectangle(190, 355, 490, 357, fill='#203346', outline='')
        self.progress = c.create_rectangle(190, 355, 190, 357, fill='#6cf3db', outline='')
        c.create_text(28, 405, text=f'v{version}  /  EXPERIMENTAL NETWORK', anchor='w',
                      fill='#6c899d', font=('Segoe UI', 8))
        self.skip = tk.Button(self.window, text='Open wallet  >', command=self.finish,
                              bg='#101e2c', fg='#bcdfec', activebackground='#203346',
                              activeforeground='#ffffff', relief='flat', bd=0,
                              font=('Segoe UI', 9), cursor='hand2', padx=10, pady=5)
        self.skip.place(relx=1, rely=1, x=-20, y=-12, anchor='se')
        self.window.lift()
        self.window.focus_set()
        self.tick()

    def tick(self):
        if self.closed:
            return
        elapsed = time.monotonic() - self.started
        progress = min(1, elapsed / self.duration)
        for index, arc in enumerate(self.orbits):
            self.canvas.itemconfigure(arc, start=(elapsed * (65 if index % 2 == 0 else -48) + index * 100) % 360)
        eased = 1 - (1 - progress) ** 3
        self.canvas.coords(self.progress, 190, 355, 190 + 300 * eased, 357)
        if progress >= 1:
            self.finish()
        else:
            self.timer = self.owner.after(25, self.tick)

    def finish(self):
        if self.closed:
            return
        self.closed = True
        if self.timer is not None:
            self.owner.after_cancel(self.timer)
        self.window.destroy()
        self.owner.deiconify()
        self.owner.lift()


def show_splash(owner, version):
    # A persistent environment option permits motion-free startup.
    if os.environ.get('PAWQUANTA_REDUCED_MOTION') == '1':
        owner.deiconify()
        return None
    return LaunchSplash(owner, version)

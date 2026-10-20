"""Short, dependency-free startup animation for the desktop wallet."""
import math
import os
import time
import tkinter as tk


def enable_native_pixels():
    """Prevent Windows from bitmap-stretching the application on high-DPI screens."""
    if os.name == 'nt':
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            pass


class LaunchSplash:
    def __init__(self, owner, version, duration=2.6):
        self.owner = owner
        self.duration = duration
        self.started = time.monotonic()
        self.closed = False
        self.timer = None
        self.window = tk.Toplevel(owner)
        self.window.title('Pawquanta - Starting')
        self.window.resizable(False, False)
        self.window.configure(bg='#080d17')
        # Vector geometry is drawn straight into the native display canvas.
        # No bitmap frames are stretched; a 4K screen gets 3840 x 2160.
        sw, sh = owner.winfo_screenwidth(), owner.winfo_screenheight()
        native_4k = sw >= 3840 and sh >= 2160
        self.scale = min(3840 / 680, sw * .88 / 680, sh * .82 / 430)
        if native_4k:self.scale = 2160 / 430
        width, height = round(680 * self.scale), round(430 * self.scale)
        if native_4k:width, height = 3840, 2160
        x = max(0, (owner.winfo_screenwidth() - width) // 2)
        y = max(0, (owner.winfo_screenheight() - height) // 2)
        self.window.geometry(f'{width}x{height}+{x}+{y}')
        if native_4k:self.window.overrideredirect(True)
        self.offset_x = (width-680*self.scale)/2
        self.window.protocol('WM_DELETE_WINDOW', self.finish)
        self.window.bind('<Escape>', lambda event: self.finish())
        self.canvas = tk.Canvas(self.window, width=width, height=height,
                                background='#080d17', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        c = self.canvas
        width, height = 680, 430
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
        c.create_oval(309, 146, 371, 191, fill='#112d35', outline='', tags='emblem')
        for dx, dy, radius in ((-29, -10, 11), (-11, -26, 12), (12, -26, 12), (30, -10, 11)):
            c.create_oval(340+dx-radius, 143+dy-radius, 340+dx+radius, 143+dy+radius,
                          fill='#112d35', outline='', tags='emblem')
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
        # Deterministic flight paths converge onto the paw silhouette.
        c.create_rectangle(-self.offset_x/self.scale,0,0,430,fill='#080d17',outline='')
        c.create_rectangle(680,0,680+self.offset_x/self.scale,430,fill='#080d17',outline='')
        self.flights = []
        shapes = [(340, 168.5, 31, 22.5)] + [(340+dx,143+dy,r,r) for dx,dy,r in ((-29,-10,11),(-11,-26,12),(12,-26,12),(30,-10,11))]
        for index in range(96):
            cx, cy, rx, ry = shapes[index % len(shapes)]
            angle = index * 2.3999632297
            target = (cx + rx * math.cos(angle), cy + ry * math.sin(angle))
            origin = (340 + 440 * math.cos(angle+.6), 165 + 310 * math.sin(angle+.6))
            glow = c.create_line(0,0,0,0,fill='#143e50',width=4)
            line = c.create_line(0,0,0,0,fill='#71fce3' if index%3 else '#729cff',width=1)
            self.flights.append((glow,line,origin,target,(index%16)*.018))
        c.scale('all',0,0,self.scale,self.scale)
        c.move('all',self.offset_x,0)
        self.fonts=[]
        for item in c.find_all():
            if c.type(item)=='text':
                from tkinter import font
                spec=font.Font(font=c.itemcget(item,'font'))
                spec.configure(size=max(7,round(spec.cget('size')*self.scale)))
                self.fonts.append(spec)
                c.itemconfigure(item,font=spec)
            elif c.type(item) in ('line','arc'):
                c.itemconfigure(item,width=float(c.itemcget(item,'width'))*self.scale)
        self.skip.configure(font=('Segoe UI',max(9,round(9*self.scale))))
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
        assembly = min(1, progress / .75)
        for glow,line,origin,target,delay in self.flights:
            t=max(0,min(1,(assembly-delay)/(1-delay)))
            ease=1-(1-t)**3
            tail=max(0,ease-.11*(1-t))
            bend=math.sin(t*math.pi)*35
            coords=[]
            for fraction in (tail,ease):
                coords.extend(((origin[0]+(target[0]-origin[0])*fraction+bend)*self.scale+self.offset_x,
                               (origin[1]+(target[1]-origin[1])*fraction-bend*.4)*self.scale))
            self.canvas.coords(glow,*coords);self.canvas.coords(line,*coords)
            if t>=1:self.canvas.itemconfigure(glow,state='hidden');self.canvas.itemconfigure(line,state='hidden')
        intensity=max(0,min(1,(assembly-.45)/.55))
        color='#'+''.join(f'{round(a+(b-a)*intensity):02x}' for a,b in zip((17,45,53),(108,243,219)))
        self.canvas.itemconfigure('emblem',fill=color)
        eased = 1 - (1 - progress) ** 3
        self.canvas.coords(self.progress,190*self.scale+self.offset_x,355*self.scale,(190+300*eased)*self.scale+self.offset_x,357*self.scale)
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

"""Shared ttk scrollbar elements without replacing native scroll bindings."""
import math
import tkinter as tk


def setup_scrollbars(root, style, colors):
    # Keep images on the Tk owner: Tcl elements retain image names, not objects.
    owner = root._root()
    scale = max(1, float(root.tk.call('tk', 'scaling')) / (96 / 72))
    thickness = round(12 * scale)
    length = round(24 * scale)
    inset = round(3 * scale)
    radius = round(3 * scale)
    images = []
    for orient in ('Vertical', 'Horizontal'):
        states = []
        for color in ('#AEB8C6', '#DCE2EA', '#667085', '#8794A6'):
            width, height = (thickness, length) if orient == 'Vertical' else (length, thickness)
            image = tk.PhotoImage(master=root, width=width, height=height)
            for y in range(inset, length - inset):
                distance = max(inset + radius - y - .5, y + .5 - (length - inset - radius), 0)
                edge = round(radius - math.sqrt(max(0, radius * radius - distance * distance)))
                for x in range(inset + edge, thickness - inset - edge):
                    point = (x, y) if orient == 'Vertical' else (y, x)
                    image.put(color, to=point)
            images.append(image)
            states.append(image)
        trough = f'Ccz.{orient}.Scrollbar.trough'
        thumb = f'Ccz.{orient}.Scrollbar.thumb'
        style.element_create(trough, 'from', 'clam', f'{orient}.Scrollbar.trough')
        style.element_create(thumb, 'image', states[0], ('disabled', states[1]),
                             ('pressed', states[2]), ('active', states[3]),
                             border=inset + radius, sticky='nswe')
        name = f'{orient}.TScrollbar'
        style.layout(name, [(trough, {'sticky': 'nswe', 'children': [
            (thumb, {'sticky': 'nswe'})]})])
        style.configure(name, troughcolor=colors['page'], borderwidth=0,
                        bordercolor=colors['page'], lightcolor=colors['page'],
                        darkcolor=colors['page'], relief='flat', arrowsize=0, width=thickness)
    owner._ccz_scrollbar_images = images
    owner._ccz_scrollbar_width = thickness


def scrollbar_width(widget):
    return getattr(widget._root(), '_ccz_scrollbar_width', 12)

import customtkinter
from PIL import Image, ImageTk
    
window = customtkinter.CTk()
    
button_image = customtkinter.CTkImage(Image.open("C:/Users/HinaLappy/Downloads/github.png"), size=(26, 26))
    
image_button = customtkinter.CTkButton(master=window,text="",width=3,image=button_image)
image_button.pack()
    
window.mainloop()

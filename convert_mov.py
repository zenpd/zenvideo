import subprocess
import static_ffmpeg
static_ffmpeg.add_paths()
 
input_file = r"C:\Users\NB125520\Downloads\Text_To_Audio\zenvideo\new.mov"  
output_file = r"C:\Users\NB125520\Downloads\Text_To_Audio\zenvideo\new_output.mp4"
 
subprocess.run([
    "ffmpeg", "-i", input_file,
    "-c:v", "copy", "-c:a", "aac",
    output_file
])
 
print("Done!")
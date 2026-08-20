import subprocess
import static_ffmpeg
static_ffmpeg.add_paths()
 
subprocess.run([
    "ffmpeg",
    "-f", "concat",
    "-safe", "0",
    "-i", "concat_list.txt",
    "-c", "copy",
    "ISO_Wrapper_Short_Demo.mp4"
])
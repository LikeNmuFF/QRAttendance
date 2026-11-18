DFPLAYER MINI - 14 MALE VOICE ANNOUNCEMENTS

IMPORTANT: Upload the updated firmware/AttendanceCam sketch once before using this set.
This updated sketch selects all 14 messages, including Present/0001, Late/0005, Absent/0006.
Old firmware uses 0001 for ALL three saved outcomes, so it will incorrectly say present for Late/Absent.

LEDs: Present = green GPIO12; Late = yellow GPIO4 (and onboard white flash);
Absent/errors = red GPIO15. Each external LED needs its own 330 Ohm series resistor.
GPIO12 also needs the documented 10 kOhm pull-down to GND.

Copy the mp3 folder to the ROOT of the DFPlayer microSD card (up to 32 GB, FAT16/FAT32).
Example: SD card / mp3 / 0001.mp3
Power off before inserting or removing the card. The card goes in the DFPlayer, not the ESP32-CAM.

Voice: Microsoft en-US-GuyNeural, synthetic male English voice, speaking rate -5%.
Format: MP3, 44.1 kHz, mono, 128 kbps.

RECORDINGS
0001.mp3 - Present: Your attendance has been recorded. You are present.
0002.mp3 - Already recorded: Your attendance has already been recorded.
0003.mp3 - Invalid QR card: Invalid QR card. Please use your official attendance QR card.
0004.mp3 - Saving failed: Your attendance could not be saved. Please try again or contact your instructor.
0005.mp3 - Late: Your attendance has been recorded. You are late.
0006.mp3 - Absent: Your attendance has been recorded as absent. Please speak with your instructor.
0007.mp3 - Dropped student: You are marked as dropped from this class. Please speak with your instructor.
0008.mp3 - Class not open: Attendance for this class is not open yet. Please wait.
0009.mp3 - Class ended: Attendance for this class has closed. Please speak with your instructor.
0010.mp3 - Class schedule missing: The class schedule has not been configured. Please contact your instructor.
0011.mp3 - Unreadable QR: Unable to read your QR card. Please hold it steady in front of the camera.
0012.mp3 - Connection problem: The scanner cannot connect to the attendance server. Please contact your instructor.
0013.mp3 - Camera failure: The camera could not start. Please contact your instructor.
0014.mp3 - Ready: The attendance scanner is ready. Please show your QR card.

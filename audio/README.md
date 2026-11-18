# Attendance voice recordings

Use **dfplayer-male-14-sd-card.zip** with the updated firmware in
`firmware/AttendanceCam`. It contains all 14 tracks in the root `mp3` folder.
The exact event/text mapping is in `dfplayer-male-14/messages.json`.

Upload the updated firmware once. Present = 0001/green GPIO12,
Late = 0005/yellow GPIO4 (plus onboard white flash), Absent = 0006/red GPIO15.
Other events use the remaining numbered tracks documented in the firmware README.

`dfplayer` and `dfplayer-male` (and their older ZIP files) are legacy packages.
They do not supply the complete 14-track mapping; do not mix their tracks with
this set. In particular, the old optional 0005-0007 meanings differ.

Use a supported FAT16/FAT32 card of up to 32 GB in the DFPlayer. Power off before
inserting or removing it. Audio playback and LED wiring still need physical testing.

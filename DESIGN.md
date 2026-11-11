# QR Attendance interface

## Direction

A dark, futuristic attendance workspace chosen by the user. Deep navy surfaces, restrained mint/cyan accents, precise typography and a dimensional scanner illustration connect the hardware to the website. The public landing page explains the workflow; the administrator dashboard prioritizes daily attendance, class time and printable student cards.

## Navigation and product truth

- `/` is a public product landing page; it never queries or exposes student data.
- `/dashboard` is the signed-in workspace. `/login` and `/logout` handle administrator access.
- Sidebar links include Classes & sessions (`/classes`) and navigate to Attendance (`/dashboard`), Students & QR cards (`/students`), Calendar (`/calendar`), and Absence audit (`/audit`). Daily review pages (`/attendance/YYYY-MM-DD`) show class hours, the eligible roster, scan times, and teacher corrections. Reports download from the existing CSV endpoint.
- Counts come from the selected date and real database records. They are not sample metrics.
- The landing scanner and sample student card are explicitly illustrative. They do not report connection status or live scans, and the decorative QR is not a student registration.
- Attendance rules remain unchanged: not open before start, Present under 15 minutes, Late from 15 to under 40 minutes, Absent at 40 minutes or more. One start time/check-in per student per session per day. Classes have separate rosters; all sessions in a class share its roster.
- A teacher explicitly finalizes completed class days to mark missing eligible students absent. Only finalized session absences count toward the four-absence drop rule within the selected class. Teachers can grant a chance, explicitly drop a student, or restore the default rule; every decision requires a saved reason. Historical records and corrections remain visible.

## Visual tokens

| Role | Value |
|---|---|
| Page | `#0c131b` |
| Surface | `#121e28` |
| Raised surface | `#192832` |
| Primary text | `#eff5f5` |
| Secondary text | `#a6b7c3` |
| Boundary | `#2c3d49` |
| Primary action | `#a9efc6` |
| Primary action text | `#092d20` |
| Focus / accent | `#75d8e7` |
| Late text | `#f4c58c` |
| Error text | `#ffc0bc` |

All status badges include text. Present is mint, Late is amber, Absent is muted red, and neutral is slate. Use shared component classes instead of choosing a new color for each screen. Controls have 44px or larger targets, visible keyboard focus, and distinct pressed/disabled states.

## Typography and assets

Space Grotesk is the heading family; DM Sans is the body/accent family, coordinated using the Font Pairing: Design & Brands plugin. Files are self-hosted under `python/attendance/static/fonts` with `font-display: swap` and local license files. Both come from the official Google Fonts repository:

- https://github.com/google/fonts/tree/main/ofl/spacegrotesk
- https://github.com/google/fonts/tree/main/ofl/dmsans

The scanner, lenses, LCD, sample card and speaker are authored HTML/CSS/SVG. No stock imagery or image-generation dependency is required. Real student QR images are generated locally by the existing Python QR endpoint. Shared outlined SVG icons are defined in `templates/components.html`.

## Motion and progressive enhancement

The landing has two coordinated floating objects and subtle pointer tilt using CSS perspective/3D transforms. The landing has no visible animation control, as requested. Motion stops for `prefers-reduced-motion`, when offscreen, and while the tab is hidden. Tablet layouts use a static variant. There is no scroll hijacking or animation blocking a primary action.

`static/app.js` adds password visibility, local table searches, active navigation state, and pending form states. Native links, date/time fields, and server forms remain the underlying interaction model. Without JavaScript, sign-in, registration, schedule changes, reports, QR display/download, and normal browser printing remain available; local search and the print-dialog button are enhancements.

## Responsive and print

At narrow widths, sidebar navigation becomes a compact top navigation, summary counts become a two-column grid, and forms stack. Attendance/registry tables scroll within their regions. QR cards retain a white background and the quiet zone on screen and paper. Print CSS removes controls, preview surfaces and site branding outside the actual card.

## Design reference

AI Graphic Design / Superdesign generated one approved dark landing direction, then exact factual corrections were imported as version 2. The Flask implementation uses native styles and interactions rather than importing the concept's CDN dependencies.

Canvas: https://superdesign.dev/teams/c3442458-2e66-453e-a5c3-40787042ed3a/projects/74547bba-040c-426b-ba93-a7a787770a7c

Draft: https://p.superdesign.dev/draft/558bb51e-b312-4692-827b-dbc4f8394ae4

Student cards now contain server-signed credentials. The print page includes a deliberately disclosed replacement action that revokes all old copies. The full student name remains on screen/paper; the scanner response shortens the name for its 16-character LCD row.


The dashboard scanner panel now includes a square aiming guide and plain-text recent scan feedback. It keeps the medium column size while using a VGA grayscale capture. Saved attendance rows, counts and feedback refresh in place about every two seconds; camera controls, search text and form input remain stable. Hidden tabs pause refresh, and connection failures remain visible. A decoded QR, a saved attendance record and a registered student are separate states in the interface.


The current scanner uses native color JPEG capture with laptop/OpenCV QR decoding. The medium preview shows those same frames; stopping preview does not stop scanning. Saved attendance, duplicates, unreadable patterns and rejected cards remain separate messages. Physical indicators use green only for a confirmed save and red for rejection/failure, with the LCD and DFPlayer result driven by the returned server status.

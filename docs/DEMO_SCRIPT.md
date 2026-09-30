# Roshan Mustaqbil: demo script

A complete script for presenting the app in about 20 minutes. It tells one
story, a day at the centre, and one person runs everything: the centre's
**administrator**, who marks attendance at the desk, enrolls walk-ins, calls
students who have stopped coming, and looks at the bigger picture.

Each section says what to **say**, what to **do**, and what the audience
**will see**. The students named are always the same after a fresh seed;
numbers and dates move with the day the demo data was loaded, so the script
gives them as "about".

| | |
|---|---|
| Length | About 20 minutes, plus questions |
| Sign-in | `admin` / `Admin123` (the only account) |
| On this PC | http://127.0.0.1:8001 |
| Shared link | The dev tunnel link (see `docs/DEPLOYMENT_OPTIONS.md`, section 1) |
| Have ready | `docs/demo/sample-students.csv`, for the import step |

The one idea to land: **students enroll in person at the centre.** There's
no online sign-up, so the day a student enrolls is their first visit, and the
question the centre cares about is who comes back.

---

## Part A: Getting ready

### The day before

1. Put the demo data in a known state:

   ```bash
   .venv\Scripts\python manage.py seed_youth_centre_demo --reset
   ```

   This recreates the 960 demo students and removes anyone added during
   earlier rehearsals (walk-ins, imported students).

2. Change the password if the link will be shared beyond the audience:
   `.venv\Scripts\python manage.py changepassword admin`. The script below
   assumes `Admin123`.

### 30 minutes before

1. Double-click **Start RM demo** (`scripts\start_demo.bat`). It:
   - adds today's check-ins so far (the demo centre opens at 9, busiest
     around 10), so "Present today" looks real;
   - checks the data (`review_rm` should end with "0 failed");
   - opens two windows, **RM demo server** and **RM public link**: keep
     both open for the whole demo;
   - opens the app in your browser.
2. Sign in as `admin` / `Admin123`.
3. Browser zoom at 100%, window at least 1280 pixels wide, other tabs closed.
   Light theme is easiest on a projector.
4. If people will follow on their own devices, send them the link. The first
   time, they see a "dev tunnel" notice page: they click **Continue**.

### 5 minutes before

- Open **Dashboard** and check the numbers look alive (someone present
  today, a trend line, "Waiting for a call").
- Close any open menus or messages. Start the demo on the dashboard or the
  sign-in page.

---

## Part B: The demo

### 1. The question (1 minute)

**Say:**
> "Around 960 young people have enrolled at Roshan Mustaqbil, always in
> person at the centre, but only about 230 have come in the last month. The
> centre needs three things: mark who comes each day, understand who they
> are and what they need, and find out what happened to everyone else,
> starting with new students who haven't come back."

**Say:** "One person runs this app: the centre's administrator. There's one
sign-in, and it does everything."

### 2. The sign-in and the look (1 minute)

**Do:** show the sign-in page, then sign in.

**They'll see:** the RM mark over the Kupwara hills, and one glass panel.
Every screen sits on the same morning backdrop with frosted-glass panels.

**Do:** click the **moon** button (top right) to show the night version,
then the **light bulb** button (same place) to come back.

### 3. The desk in the morning (4 minutes)

**Do:** menu **Attendance > Mark attendance**.

**Say:** "This is the screen the desk keeps open all day. One search box."

1. **A new student walks in.**
   - **Do:** type `Rafiq Sheikh`. **They'll see:** no match.
   - **Do:** click **enroll them as a new student**. The name is already
     filled in.
   - **Say:** "Students enroll in person, so enrolling also marks them
     present. There's no online form."
   - **Do:** show the sections: Student details, Goal and studies, Why they
     came, Guardian. Point out "date of birth, or approximate age".
   - **Do:** fill in phone `9419000123`, gender **Male**, age `19`. For
     career goal pick **Defence**: the entry-scheme question appears only
     then; pick **NDA**.
   - **Do:** **Enroll and mark present**.
   - **They'll see:** back at the desk, "Rafiq Sheikh is enrolled… and
     marked present", and he's in today's list with an **Enrolled** tag
     instead of a remove button.
   - **Say:** "The enrollment day always counts as a visit, so it can't be
     deleted by accident."
2. **Duplicate check.**
   - **Do:** menu **Students > Enroll student**: name `Yasir Dar`, phone
     `9419690461`, gender **Male**, age `20`, **Enroll and mark present**.
   - **They'll see:** "This may be a student who's already enrolled", with a
     link to Yasir Dar (RM-0404). **Do:** click **Cancel**.
3. **A student comes back after months away.**
   - **Do:** back at **Mark attendance**, type `RM-0018` and press
     **Enter**.
   - **They'll see:** "Mehak Hajam is marked present at 10:xx", and the box
     clears for the next student.
   - **Say:** "She hadn't been in for over two months. Typing alone never
     marks anyone; only Enter does, and only for an exact registration or
     phone number."
   - **Do:** click **Undo** in the green message. The mark is removed.
4. **By name.**
   - **Do:** type `bhat`. **They'll see:** matching students with guardian
     and area, so two students with the same name can be told apart, and
     "Showing 8 of 99 matches. Keep typing to narrow it down."
5. **Siblings on one phone.**
   - **Do:** type `9419419259` and press **Enter**.
   - **They'll see:** nobody is marked: Aadil Dar and Mudasir Dar share this
     number, so you choose the right one.
6. **Regulars not in yet.**
   - **Do:** clear the box. **They'll see:** students who came 3 or more
     times in the last two weeks but not today, each with one-click **Mark
     present**.
7. **A paper register from a missed day.**
   - **Do:** change **Marking attendance for** to yesterday. **They'll
     see:** the box turns saffron; marks are saved for that day, without a
     time. **Do:** change it back to today (**Back to today**).

### 4. The dashboard (3 minutes)

**Do:** menu **Dashboard**.

1. **The headline.** "About 230 of the centre's 880 current students came
   in the last 30 days", with the change against 30 days ago.
   **Say:** "The line shows the rise to a July peak and the fall since.
   That's the story this app helps the centre act on."
2. **The legend** gives plain definitions: **Active** (came in the last 30
   days), **Slipping away** (30–59 days), **Inactive** (60+ days) and **Moved
   on** (selected, joined a course, moved away, stopped).
   **Say:** "Students who were selected or joined a course don't count as
   failures; they've moved on."
3. **The four numbers:**
   - *Present today, so far*, against a typical open day by this time.
   - *Visits per active student*, for students enrolled over a month ago.
   - *Enrolled this month*: how many of those who enrolled over a week ago
     have come back, and how many enrolled too recently to tell.
   - *Waiting for a call* (about 430): the total of the four call lists.
     **Say:** "It's the same number on the call list and in the downloaded
     call sheet."
4. **Who to call** lists the four call lists, easiest to win back first.
5. **What happened to students who stopped coming**: the saffron bar is
   students not contacted yet; the rest is what calls found out (studying,
   preparing at home, employed, selected, moved away).
   **Do:** click any bar: it opens the list of those students.

### 5. Follow-up calls (3 minutes)

**Do:** on the dashboard, **Open the call list**.

1. **Say:** "The first list is **New students who didn't come back**:
   students who enrolled one to eight weeks ago and haven't returned. A call
   in the first weeks brings many of them back." Then come **Regulars who
   missed this week**, **Slipping away** and **Inactive**. Older students who
   only came to enroll are on the Inactive list, tagged **Only came to
   enroll**.
2. Each row shows the phone number (tap to call on a phone), the guardian's
   number, when they enrolled or last came, and the last call.
3. **Do:** on the first student, choose **Plans to come back**, type "Will
   come on Monday", **Save & next**.
   **They'll see:** the row turns into a confirmation, "Waiting for a call"
   and the tab count go down by one, and the cursor moves to the next
   student.
   **Say:** "They'll come back to the list in 14 days if they haven't
   returned. Students who couldn't be reached come back after 7."
4. The numbers at the top show whether calling works: calls this week, how
   often the student was reached, and **came back after a call**.

### 6. Students (2 minutes)

**Do:** menu **Students > All students**.

1. **Do:** **More filters**, choose **Came back after enrolling: No**, then
   **Area: Handwara**. **Say:** "A call list for someone visiting Handwara."
   Each filter shows as a chip you can remove.
2. **Do:** **Download CSV**. **Say:** "It opens in Excel with Urdu and Hindi
   names intact, with visits, whether they came back after enrolling,
   guardian numbers, the last call and which call list they're on."
3. **Do:** search `RM-0290` and open **Aadil Dar**.
   **They'll see:** a banner: he enrolled about six weeks ago, hasn't been
   back since, and when he was last called (he's studying at school /
   college). His one visit is labelled **Enrolled**. There's a 12-month visit
   calendar and the call history.
4. **Do:** search `RM-0198` and open **Arif Rather** (moved on: selected).
   **Say:** "He's no longer counted as inactive. **They're still a current
   student** undoes it, and a check-in brings a student back automatically."
5. **Say:** "**Edit details** has **Remove this student**, for someone
   enrolled by mistake, a duplicate for example." Don't click it.

### 7. Understanding the centre (3 minutes)

1. **Do:** menu **Attendance > Attendance dashboard**.
   **They'll see:** daily visits, the busiest days of the week (closed on
   Sundays) and times of day (a morning peak around 10), the most regular
   students, and how often each goal group comes. **Do:** switch between 30,
   60 and 90 days.
2. **Do:** menu **Career goals**.
   **They'll see:** each goal group (Defence, UPSC / Civil Services, NEET UG,
   NEET PG, Other) split into active, slipping away and inactive; Defence
   entry schemes (NDA, TES, CDS, AFCAT, Agniveer, TA / JKLI); and other
   exams (JKSSB, JKAS, JEE, banking and more).
3. **Do:** menu **Analytics**.
   - It opens on **Active students**; switch to **Everyone enrolled** to
     compare, and filter by goal.
   - **New enrollments, and whether they came back**: green came back,
     saffron only came to enroll, grey enrolled in the last 7 days (too
     early to tell).
   - **How long students kept coming before they stopped**, counted from
     the day they enrolled. **Say:** "About a third stop within their first
     month, and the largest group kept coming for six months or more. So
     both the first weeks and long-time students are worth a call."
   - **Support they need** (compared with students who stopped), **Where they
     come from** by tehsil, **What students expect from RM** in their own
     words, and **Details to complete** for missing data.
   - Most bars open the matching list of students.

### 8. Bringing in the paper register (1 minute)

**Do:** menu **Students > Import from a spreadsheet**.

1. **Say:** "This is how the existing paper register gets in."
2. **Do:** **Download the template** (show it), then choose
   `docs/demo/sample-students.csv` and **Check the file**.
   **They'll see:** 2 to add, 1 already enrolled (skipped), 1 to fix (bad
   phone number, no enrollment date).
   **Say:** "Because students enroll in person, the enrollment date is
   required, and each imported student is recorded as present that day."
3. **Do:** **Import 2 students**.
4. **Say:** "The **Past attendance** tab does the same for old attendance
   registers, and flags any visit dated before a student enrolled."

### 9. Close (30 seconds)

**Say:**
> "So: the desk marks attendance in seconds, every enrollment is a first
> visit, the call lists tell you who to call first, and the dashboards show
> who's coming, who's slipping away and what happened to them. One
> administrator runs it all."

---

## Part C: Questions people ask

- **Can students enroll online?** No. They enroll in person at the centre,
  which is why enrolling marks them present.
- **Do students get a login?** No. Students are records; only the
  administrator signs in.
- **Can more staff use it?** It's set up for one administrator who does
  everything. Anyone else who signs in sees a "no access" page.
- **How is a student's progress tracked?** Three ways, each with a clear
  source: attendance (recorded at the desk), their goal (entered once at
  enrollment), and follow-up calls (what they're doing now, and whether they
  were selected or joined a course). Nobody has to keep a progress score up
  to date.
- **What if the internet drops?** The desk shows "Not saved: the connection
  dropped", and the mark can be tried again. Nothing is silently lost.
- **Can we correct mistakes?** Undo or remove any mark. If an enrollment date
  was wrong, correct it on the student's details and the enrollment visit
  moves with it. A student enrolled by mistake can be removed.
- **What counts as an open day?** A day with at least 5 visits, so a stray
  mark on a Sunday doesn't count.
- **Can it use our existing register?** Yes, through the spreadsheet import.
- **Where does it run?** Here on this PC for the demo, shared through a
  secure link. For daily use it can be hosted online; see
  `docs/DEPLOYMENT_OPTIONS.md`.

---

## Part D: If something goes wrong

| What you see | What to do |
|---|---|
| The page doesn't load at all | Check the two windows, **RM demo server** and **RM public link**, are still open. If not, double-click **Start RM demo** again. The link stays the same. |
| A "dev tunnel" notice page | Normal for the shared link the first time: click **Continue**. |
| "Your account is locked" after wrong passwords | `.venv\Scripts\python manage.py axes_reset` |
| "Present today" is 0 or very low | Early in the day. Run `.venv\Scripts\python manage.py seed_youth_centre_demo` (it only adds check-ins so far), then reload. |
| Rafiq Sheikh or the imported students are already there | A rehearsal wasn't reset: see Part E. |
| Something looks old after an update | Reload the page (Ctrl+R). |

---

## Part E: After the demo

Put the demo data back as it was. This also removes Rafiq Sheikh, the two
imported students and anyone else added during the demo:

```bash
.venv\Scripts\python manage.py seed_youth_centre_demo --reset
```

Close the two windows to stop the app and the shared link.

---

## Cheat sheet

| Step | Type or pick | Expect |
|---|---|---|
| New walk-in | `Rafiq Sheikh`, phone `9419000123`, Male, age `19`, Defence, NDA | No match, then enrolled and marked present |
| Duplicate warning | phone `9419690461` | Links to Yasir Dar (RM-0404) |
| Back after months | `RM-0018`, Enter | Mehak Hajam (away over two months) marked present; Undo |
| Name search | `bhat` | 8 of 99 matches, "keep typing" |
| Shared phone | `9419419259`, Enter | Aadil Dar and Mudasir Dar; nobody marked |
| Didn't come back | `RM-0290` | Aadil Dar: enrolled about six weeks ago, not back since, called once |
| Moved on | `RM-0198` | Arif Rather, selected |
| Import | `docs/demo/sample-students.csv` | 2 to add, 1 already enrolled, 1 to fix |

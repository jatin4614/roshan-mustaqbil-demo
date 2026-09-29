# Roshan Mustaqbil: demo script

A walkthrough of about 15 minutes, told as a day at the centre. One person
runs the app: the centre's **administrator**, who marks attendance at the
desk in the morning, calls students who have stopped coming, and looks at the
bigger picture. There is one sign-in, and it can do everything.

One idea runs through the app: **students enroll in person at the centre.**
There is no online sign-up. The day a student enrolls is their first visit,
so every enrolled student has come at least once. The question the centre
cares about is who comes back.

Numbers change with the date and time of day. The ones below are examples;
the students named are always the same after a fresh seed.

## Before the demo

1. Start the app (from `O:\RM\horilla-hr`):

   ```bash
   .venv\Scripts\python manage.py runserver 127.0.0.1:8001
   ```

   To show it on other devices, share a link (see `docs/DEPLOYMENT_OPTIONS.md`,
   section 1: VS Code port forwarding).

2. Fill in today's check-ins so far (run it shortly before the demo; it only
   adds visits for students who are still coming):

   ```bash
   .venv\Scripts\python manage.py seed_youth_centre_demo
   ```

3. Check the data: `.venv\Scripts\python manage.py review_rm` should end
   with "0 failed".

4. Go to `http://127.0.0.1:8001` and sign in as `admin` / `Admin123`.

5. Have `docs/demo/sample-students.csv` ready for the import step.

## 1. The question (30 seconds)

> "Around 960 young people have enrolled at Roshan Mustaqbil, always in
> person at the centre, but only 150 to 250 come regularly. The centre needs
> to mark who comes each day, understand who they are and what they need,
> and find out what happened to everyone else, starting with the newest
> students who haven't come back."

## 2. The sign-in and the look (30 seconds)

1. The sign-in page: the RM mark over the Kupwara hills, and one glass
   panel. There's one account: the administrator's.
2. Every screen sits on the same morning backdrop, with frosted-glass
   panels. The moon button (top right) switches to a night version.

## 3. The desk in the morning (3 minutes)

1. **Attendance > Mark attendance**. One big search box.
2. **A new student walks in.** Type `Rafiq Sheikh`: no match. Click **enroll
   them as a new student**; the name is already filled in.
   - The page says it plainly: students enroll in person, so enrolling also
     marks them present.
   - Show the sections: goal, exam and preparation stage; the Defence entry
     question that appears only when the goal is Defence; "date of birth, or
     approximate age".
   - **Enroll and mark present** saves the student and records today as their
     first visit. Back at the desk, he's in today's list with an **Enrolled**
     tag instead of a remove button: the enrollment day can't be deleted on
     its own.
   - Try enrolling with an existing phone number (`9419690461`): the form
     warns the student may already be enrolled and links to Yasir Dar.
3. **A student comes back after months away.** Type `RM-0018` and press
   **Enter**. Mehak Hajam, who hasn't been in since July, is marked present
   with the time, and the box clears for the next student. (Typing alone
   never marks anyone; only Enter does.)
   - Press **Undo** in the green message: the mark is removed.
4. **By name.** Type `bhat`. The list shows guardian and area, so two
   students with the same name can be told apart, and says how many more
   match: keep typing to narrow it.
5. **Siblings on one phone.** Type `9419419259` and press **Enter**. Nobody
   is marked: Aadil Dar and Mudasir Dar share this number, so you choose the
   right one.
6. **Regulars not in yet.** Clear the box: students who came 3 or more times
   in the last two weeks but not today, each with one-click **Mark present**.
7. **A missed day.** Change "Marking attendance for" to yesterday: the box
   turns saffron, and marks are saved for that day without a time. Change it
   back to today.

## 4. The dashboard (3 minutes)

1. **Dashboard** in the menu. **The headline.** "About 230 of the centre's
   880 current students came in the last 30 days", with the change against
   30 days ago. The six-month line shows the rise to a July peak and the fall
   since: something worth acting on.
2. The legend gives plain definitions: **Active** (came in the last 30
   days), **Slipping away** (30–59 days), **Inactive** (60+ days) and **Moved
   on** (selected, joined a course, moved away, stopped). Moved-on students no
   longer count as failures.
3. **The four numbers**:
   - *Present today, so far* against *a typical open day by this time*.
   - *Visits per active student*: the typical number, counting students
     enrolled over a month ago (newer ones haven't had a month yet).
   - *Enrolled this month, so far*: how many of those who enrolled over a
     week ago **have come back**, and how many enrolled too recently to tell.
   - *Waiting for a call*: the total of the four call lists. It's the same
     number on the call list and in the downloaded call sheet.
4. **Who to call** lists the four call lists, easiest to win back first.
   **What happened to students who stopped coming** answers the centre's
   question: the saffron bar is those not contacted yet; the rest is what
   calls found out (studying, preparing at home, employed, selected, moved
   away). Click any bar for the list of students.

## 5. Follow-up calls (3 minutes)

1. Click **Open the call list**. The first tab is **New students who didn't
   come back**: students who enrolled 7 to 60 days ago and haven't been back
   (Sajad Shah, enrolled a week ago, is at the top). A call in the first
   weeks brings many of them back. Then come **Regulars who missed this
   week**, **Slipping away** and **Inactive**. Older students who only came
   to enroll are on the Inactive list, tagged "Only came to enroll".
2. Each row has the phone number (tap to call on a phone), the guardian's
   number, when they enrolled or last came, and the last call.
3. Log a call: choose **Plans to come back**, type a note, **Save & next**.
   The row turns into a confirmation, the counts at the top and on the tabs
   go down, and the cursor moves to the next student. This student comes back
   to the list in 14 days if they haven't returned; students who couldn't be
   reached come back after 7.
4. The numbers at the top show whether calling works: calls this week, how
   often the student was reached, and **came back after a call**.

## 6. Students (2 minutes)

1. **Students > All students**. Open **More filters** and choose **Came back
   after enrolling: No**, then **Area: Handwara**: a call list for someone
   visiting Handwara. Each filter shows as a removable chip.
2. **Download CSV** gives the list as a call sheet, with visits, whether they
   came back after enrolling, guardian numbers, last contact, notes and which
   call list they're on. It opens in Excel with Urdu and Hindi names intact.
3. Open **Aadil Dar** (RM-0290): the banner says he enrolled on 19 August,
   hasn't been back since, and when he was last called. The first visit in
   his list is labelled **Enrolled**; there's also the 12-month visit
   calendar and the call history.
4. Open a moved-on student, such as **Arif Rather** (RM-0198, selected). The
   banner explains why he's no longer counted; **They're still a current
   student** undoes it, and a check-in also brings a student back
   automatically.
5. **Edit details** has **Remove this student** for someone enrolled by
   mistake (a duplicate, say). Don't click it in the demo.

## 7. Understanding the centre (3 minutes)

1. **Attendance > Attendance dashboard**: the busiest days (the centre is
   closed on Sundays) and hours (a morning peak around 10), how many enrolled
   this week, the most regular students, and how often each goal group comes.
   Switch between 30, 60 and 90 days.
2. **Career goals**: each goal group's split between active, slipping away
   and inactive; Defence entry schemes (NDA, TES, CDS, AFCAT, Agniveer, TA /
   JKLI) and other exams (UPSC, JKAS, JKSSB, JEE and more); how far along each
   group is in their preparation; which years their exams are in.
3. **Analytics**:
   - It opens on **Active students**, the people who actually use the centre;
     switch to **Everyone enrolled** to compare. Filter by goal.
   - **Didn't come back after enrolling** sits next to the status numbers.
   - **New enrollments, and whether they came back**: every enrollment is a
     first visit. Green came back, saffron only came to enroll, and grey
     enrolled in the last 7 days (too early to tell). Above it: how many came
     back within a week.
   - **How long students kept coming before they stopped**, counted from the
     day they enrolled. About 30% stopped within their first month; the
     largest group kept coming for six months or more before stopping. So
     both the first weeks and long-time students are worth a call.
   - **Support they need**, with the share among students who stopped for
     comparison; **Where they come from** by tehsil; **What students expect**
     in their own words; and **Details to complete** for missing data.
   - Most bars open the matching list of students.

## 8. Bringing in the paper register (1 minute)

**Students > Import from a spreadsheet** is how the paper register gets in.
**Download the template**, then choose `docs/demo/sample-students.csv` and
**Check the file**. The preview marks two rows to add, one already enrolled
(skipped) and one to fix (bad phone, no enrollment date). Because students
enroll in person, the enrollment date is required: each imported student is
recorded as present that day. **Import** adds the two students with their
original enrollment dates. The **Past attendance** tab does the same for old
attendance registers, and flags any visit dated before a student enrolled.

## Questions people ask

- **Can students enroll online?** No. They enroll in person at the centre,
  which is why enrolling marks them present.
- **Do students get a login?** No. Students are records; only the
  administrator signs in.
- **Can more staff use it?** It's set up for one administrator who does
  everything. Anyone else who signs in sees a "no access" page.
- **What if the internet drops?** The desk shows "Not saved: the connection
  dropped", and the mark can be tried again. Nothing is silently lost.
- **Can we correct mistakes?** Undo or remove any mark. If an enrollment date
  was wrong, correct it on the student's details and the enrollment visit
  moves with it. A student enrolled by mistake can be removed.
- **What counts as an open day?** A day with at least 5 visits, so a stray
  mark on a Sunday doesn't count.
- **How is a student's progress tracked?** Three ways: whether they keep
  coming (the status), where they are in their preparation (the stage, exam
  and exam year on their details), and how things turned out (selected,
  joined a course), recorded from calls.
- **Can it use our existing register?** Yes, through the spreadsheet import.

## After the demo

Put the demo data back as it was. This also removes Rafiq Sheikh, the two
imported students and anyone else enrolled during the demo:

```bash
.venv\Scripts\python manage.py seed_youth_centre_demo --reset
```

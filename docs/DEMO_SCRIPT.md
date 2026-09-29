# Roshan Mustaqbil: demo script

A walkthrough of about 15 minutes, told as a day at the centre: the front
desk in the morning, the coordinator following up on students who stopped
coming, and the manager looking at the bigger picture.

Numbers change with the date and time of day. The ones below are examples;
the students named are always the same after a fresh seed.

## Before the demo

1. Start the app (from `O:\RM\horilla-hr`):

   ```bash
   .venv\Scripts\python manage.py runserver 127.0.0.1:8001
   ```

2. Fill in today's check-ins so far (run it shortly before the demo; it only
   adds visits):

   ```bash
   .venv\Scripts\python manage.py seed_youth_centre_demo
   ```

3. Open two browser windows: a normal one and a private/incognito one, so
   you can be two people at once. Go to `http://127.0.0.1:8001`.

   | Username | Password | Role |
   |---|---|---|
   | `desk` | `Admin123` | Front desk |
   | `coordinator` | `Admin123` | Coordinator |
   | `admin` | `Admin123` | Manager |

4. Have `docs/demo/sample-students.csv` ready for the import step.

## 1. The question (30 seconds)

> "Around 960 young people have registered at Roshan Mustaqbil, but only
> 150 or so come regularly. The centre needs to mark who comes each day,
> understand who they are and what they need, and find out what happened to
> everyone else, then bring back the ones it can."

## 2. The front desk (3 minutes) — sign in as `desk`

1. **Sign-in page**: the RM logo, one clear form. Forgotten passwords go to
   the manager: there's no email to reset them.
2. The front desk lands straight on **Mark attendance**. Point out the
   sidebar: only attendance and enrollment, nothing else to get lost in.
3. **The fastest path.** Type `RM-0018` and press **Enter**. Mehak Hajam,
   who hasn't been in since July, is marked present with the time. The box
   clears, ready for the next student.
   - Press **Undo** in the green message: the mark is removed.
4. **By name.** Type `bhat`. The list shows guardian and area, so two
   students with the same name can be told apart. The note under the list
   says how many more match: keep typing to narrow it.
5. **Siblings on one phone.** Type `9419419259` and press **Enter**. Nobody
   is marked: Aadil Dar and Mudasir Dar share this number, so the desk
   chooses the right one.
6. **Regulars not in yet.** Clear the box. Students who came 3 or more times
   in the last two weeks but not today are listed with one-click **Mark
   present**.
7. **A new student walks in.** Type `Rafiq Sheikh`, then click **enroll them
   as a new student**. The name is already filled in. Show the sections,
   the Defence entry question that appears only when the goal is Defence,
   and the "date of birth, or approximate age" rule. **Enroll and mark
   present** saves and marks them in one go.
   - Try enrolling with an existing phone number (e.g. `9419690461`): the
     form warns that the student may already be enrolled and links to them.
8. **A missed day.** Change "Marking attendance for" to yesterday: the box
   turns saffron, and marks are saved for that day without a time. Change
   it back to today.
9. The **×** next to a check-in on the right removes a mistaken mark.

## 3. The coordinator's dashboard (3 minutes) — sign in as `coordinator`

1. **The headline.** "About 180 of the centre's 880 current students came in
   the last 30 days", with the change against 30 days ago (e.g. "42 fewer").
   The six-month line shows the rise to a July peak and the fall since:
   something worth acting on.
2. The legend gives plain definitions: **Active**, **Slipping away** (last
   came 30–59 days ago), **Inactive** (60+ days), **Never came**, and
   **Moved on** (selected, joined a course, moved away, stopped). Moved-on
   students no longer count as failures.
3. **The four numbers**:
   - *Present today, so far* against *a typical open day by this time*.
   - *Visits per active student*: the typical number, and how many came only
     once or twice.
   - *Enrolled this month, so far*, and how many of them have come in.
   - *Waiting for a call*: students who stopped coming and haven't been
     called since.
4. **Who to call** splits the call queue, easiest first. **What happened to
   students who stopped coming** answers the centre's question: the saffron
   bar is those not contacted yet; the rest is what calls found out (studying,
   preparing at home, employed, selected, moved away). Click any bar for the
   list of students.

## 4. Follow-up calls (3 minutes)

1. Click **Open the call list**. The tabs are the four queues: **Regulars who
   missed this week** first, because they are the easiest to bring back.
2. Each row has the phone number (tap to call on a phone), the guardian's
   number, when they last came, and the last call.
3. Log a call: choose **Plans to come back**, type a note, **Save & next**.
   The row turns into a confirmation, "Calls logged today" goes up, and the
   cursor moves to the next student. This student comes back to the list in
   14 days if they haven't returned; students who couldn't be reached come
   back after 7.
4. The numbers at the top show whether calling works: calls this week, how
   often the student was reached, and **came back after a call**.

## 5. Students (2 minutes)

1. **Students > All students**. Filter by **Status: Slipping away** and
   **More filters > Area: Handwara**: a list for someone visiting Handwara.
   Each filter shows as a chip that can be removed.
2. **Download CSV** gives the list as a call sheet, with guardian numbers,
   last contact and notes. It opens in Excel with Urdu and Hindi names intact.
3. Open a student: status, goal and exam, a 12-month visit calendar, the
   visits (with who marked each one), and the call history.
4. Open a moved-on student (Status: Moved on). The banner explains why they
   are no longer counted; **They're still a current student** undoes it, and
   a check-in also brings them back automatically.

## 6. Understanding the centre (3 minutes)

1. **Attendance > Attendance dashboard**: the busiest days (the centre is
   closed on Sundays) and hours (a morning peak around 10), the most regular
   students, and how often each goal group comes. Switch between 30, 60 and
   90 days.
2. **Career goals**: each goal group's split between active, slipping away
   and inactive; Defence entry schemes (NDA, TES, CDS, AFCAT, Agniveer, TA /
   JKLI) and other exams (UPSC, JKAS, JKSSB, JEE and more); how far along each
   group is; which years their exams are in.
3. **Analytics**:
   - It opens on **Active students**, the people who actually use the centre;
     switch to **Everyone enrolled** to compare. Filter by goal.
   - **New enrollments, and whether they came**: the grey part of each bar is
     students who enrolled but never came, with the conversion in words above.
   - **How long students kept coming before they stopped**: most who stop do
     so within their first month. The first weeks matter most.
   - **Support they need**, with the share among students who stopped for
     comparison; **Where they come from** by tehsil; **What students expect**
     in their own words; and **Details to complete** for missing data.
   - Every bar opens the matching list of students.

## 7. The manager (2 minutes) — sign in as `admin`

1. Profile menu > **Staff accounts**: who can sign in and with which role.
   Add someone as Front desk with a temporary password; they choose their
   own at first sign-in. Change a role or reset a password in the list.
2. **Students > Import from a spreadsheet**: **Download the template**, then
   choose `docs/demo/sample-students.csv` and **Check the file**. The preview
   marks two rows to add, one already enrolled (skipped) and one with a phone
   number to fix. **Import** adds the two students, with their original
   enrollment dates. The **Past attendance** tab does the same for old
   registers.

## Questions people ask

- **Do students get a login?** No. Students are records; only staff sign in.
- **What if the internet drops?** The desk shows "Not saved: the connection
  dropped", and the mark can be tried again. Nothing is silently lost.
- **Can we correct mistakes?** The desk can undo or remove today's marks;
  coordinators can remove any visit from the history or a profile.
- **What counts as an open day?** A day with at least 5 visits, so a stray
  mark on a Sunday doesn't count.
- **Can it use our existing register?** Yes, through the spreadsheet import.

## After the demo

Put the demo data back as it was:

```bash
.venv\Scripts\python manage.py seed_youth_centre_demo --reset
```

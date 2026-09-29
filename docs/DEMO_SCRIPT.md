# Roshan Mustaqbil: demo script

A walkthrough of about 15 minutes, told as a day at the centre: the front
desk in the morning, the coordinator following up on students who stopped
coming, and the manager looking at the bigger picture.

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

> "Around 960 young people have enrolled at Roshan Mustaqbil, always in
> person at the centre, but only 150 to 200 come regularly. The centre needs
> to mark who comes each day, understand who they are and what they need,
> and find out what happened to everyone else, starting with the ones who
> enrolled and never came back."

## 2. The front desk (3 minutes) — sign in as `desk`

1. **Sign-in page**: the RM logo and one clear form. Forgotten passwords go
   to the manager: there's no email to reset them.
2. The front desk lands straight on **Mark attendance**. The sidebar only has
   attendance and enrollment: nothing else to get lost in.
3. **A new student walks in.** Type `Rafiq Sheikh`: no match. Click **enroll
   them as a new student**; the name is already filled in.
   - The page says it plainly: students enroll in person, so enrolling also
     marks them present.
   - Show the sections: goal, exam and preparation stage; the Defence entry
     question that appears only when the goal is Defence; "date of birth, or
     approximate age".
   - **Enroll and mark present** saves the student and records today as their
     first visit. You're back at the desk with them in today's list.
   - Try enrolling with an existing phone number (`9419690461`): the form
     warns the student may already be enrolled and links to Yasir Dar.
4. **A regular arrives.** Type `RM-0018` and press **Enter**. Mehak Hajam,
   who hasn't been in since July, is marked present with the time, and the
   box clears for the next student.
   - Press **Undo** in the green message: the mark is removed.
5. **By name.** Type `bhat`. The list shows guardian and area, so two
   students with the same name can be told apart, and says how many more
   match: keep typing to narrow it.
6. **Siblings on one phone.** Type `9419419259` and press **Enter**. Nobody
   is marked: Aadil Dar and Mudasir Dar share this number, so the desk
   chooses the right one.
7. **Regulars not in yet.** Clear the box: students who came 3 or more times
   in the last two weeks but not today, each with one-click **Mark present**.
8. **A missed day.** Change "Marking attendance for" to yesterday: the box
   turns saffron, and marks are saved for that day without a time. Change it
   back to today.
9. The **×** next to a check-in on the right removes a mistaken mark.

## 3. The coordinator's dashboard (3 minutes) — sign in as `coordinator`

1. **The headline.** "About 230 of the centre's 880 current students came in
   the last 30 days", with the change against 30 days ago. New enrollments
   count: they came in to enroll. The six-month line shows the rise to a July
   peak and the fall since: something worth acting on.
2. The legend gives plain definitions: **Active** (came in the last 30
   days), **Slipping away** (30–59 days), **Inactive** (60+ days) and **Moved
   on** (selected, joined a course, moved away, stopped). Moved-on students no
   longer count as failures.
3. **The four numbers**:
   - *Present today, so far* against *a typical open day by this time*.
   - *Visits per active student*: the typical number, and how many came only
     once or twice.
   - *Enrolled this month, so far*, and how many **have come back since
     enrolling**.
   - *Waiting for a call*: students who stopped coming and haven't been
     called since, including how many **didn't come back after enrolling**.
4. **Who to call** lists the queues, easiest to win back first. **What
   happened to students who stopped coming** answers the centre's question:
   the saffron bar is those not contacted yet; the rest is what calls found
   out (studying, preparing at home, employed, selected, moved away). Click
   any bar for the list of students.

## 4. Follow-up calls (3 minutes)

1. Click **Open the call list**. The first tab is **Didn't come back after
   enrolling**: students who enrolled a week or more ago and haven't been back.
   A call in the first weeks is what brings most of them back. Then come
   **Regulars who missed this week**, **Slipping away** and **Inactive**.
2. Each row has the phone number (tap to call on a phone), the guardian's
   number, when they enrolled or last came, and the last call.
3. Log a call: choose **Plans to come back**, type a note, **Save & next**.
   The row turns into a confirmation, "Calls logged today" goes up, and the
   cursor moves to the next student. This student comes back to the list in
   14 days if they haven't returned; students who couldn't be reached come
   back after 7.
4. The numbers at the top show whether calling works: calls this week, how
   often the student was reached, and **came back after a call**.

## 5. Students (2 minutes)

1. **Students > All students**. Open **More filters** and choose **Came back
   after enrolling: Didn't come back after enrolling**, then **Area:
   Handwara**: a call list for someone visiting Handwara. Each filter shows as
   a removable chip.
2. **Download CSV** gives the list as a call sheet, with visits, guardian
   numbers, last contact and notes. It opens in Excel with Urdu and Hindi
   names intact.
3. Open a student who didn't come back: a banner says they enrolled on a date
   and haven't been back, and the first visit is labelled **Enrolled**. There's
   also the 12-month visit calendar, who marked each visit, and the call
   history.
4. Open a moved-on student (Status: Moved on). The banner explains why they
   are no longer counted; **They're still a current student** undoes it, and a
   check-in also brings them back automatically.

## 6. Understanding the centre (3 minutes)

1. **Attendance > Attendance dashboard**: the busiest days (the centre is
   closed on Sundays) and hours (a morning peak around 10), new enrollments
   this week, the most regular students, and how often each goal group comes.
   Switch between 30, 60 and 90 days.
2. **Career goals**: each goal group's split between active, slipping away
   and inactive; Defence entry schemes (NDA, TES, CDS, AFCAT, Agniveer, TA /
   JKLI) and other exams (UPSC, JKAS, JKSSB, JEE and more); how far along each
   group is; which years their exams are in.
3. **Analytics**:
   - It opens on **Active students**, the people who actually use the centre;
     switch to **Everyone enrolled** to compare. Filter by goal.
   - **Didn't come back after enrolling** sits next to the status numbers.
   - **New enrollments, and whether they came back**: every enrollment is a
     first visit; the saffron part of each month is students who only came to
     enroll. Above it: how many came back within a week.
   - **How long students kept coming before they stopped**, counted from the
     day they enrolled: most who stop do so within their first month, so the
     first weeks matter most.
   - **Support they need**, with the share among students who stopped for
     comparison; **Where they come from** by tehsil; **What students expect**
     in their own words; and **Details to complete** for missing data.
   - Every bar opens the matching list of students.

## 7. The manager (2 minutes) — sign in as `admin`

1. Profile menu > **Staff accounts**: who can sign in and with which role.
   Add someone as Front desk with a temporary password; they choose their own
   at first sign-in. Change a role or reset a password in the list.
2. **Students > Import from a spreadsheet**: this is how the paper register
   gets in. **Download the template**, then choose
   `docs/demo/sample-students.csv` and **Check the file**. The preview marks
   two rows to add, one already enrolled (skipped) and one to fix (bad phone,
   no enrollment date). Because students enroll in person, the enrollment date
   is required: each imported student is recorded as present that day.
   **Import** adds the two students with their original enrollment dates. The
   **Past attendance** tab does the same for old attendance registers.

## Questions people ask

- **Can students enroll online?** No. They enroll in person at the centre,
  which is why enrolling marks them present.
- **Do students get a login?** No. Students are records; only staff sign in.
- **What if the internet drops?** The desk shows "Not saved: the connection
  dropped", and the mark can be tried again. Nothing is silently lost.
- **Can we correct mistakes?** The desk can undo or remove today's marks;
  coordinators can remove any visit. If an enrollment date was wrong, correct
  it on the student's details and the enrollment visit moves with it.
- **What counts as an open day?** A day with at least 5 visits, so a stray
  mark on a Sunday doesn't count.
- **Can it use our existing register?** Yes, through the spreadsheet import.

## After the demo

Put the demo data back as it was:

```bash
.venv\Scripts\python manage.py seed_youth_centre_demo --reset
```

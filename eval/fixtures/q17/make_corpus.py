#!/usr/bin/env python3
"""Generate the frozen q17 corpus: 50 Markdown notes and 5 text-based PDFs.

Python stdlib only, deterministic (fixed seed, no timestamps in the output):

  python3 make_corpus.py            # writes corpus/ and questions.json next to this file
  python3 make_corpus.py --out DIR  # writes DIR/corpus and DIR/questions.json

Five synthetic facts each hold one made-up token. Three facts live in one
Markdown note each; two live only inside a PDF (no Markdown note holds those
tokens). Five "sibling" notes mention the same subject without the token, and
the other 42 notes and 3 PDFs are filler. Every file name is unique, and no
file name stem is contained in another, so a cited file can be found by name.

The committed corpus is the frozen copy; SHA256SUMS records its hashes and
verify_corpus.py checks them. Re-running this script must reproduce the same
bytes (verify_corpus.py --regenerate checks that too).
"""

import argparse
import json
import os
import random
import re
import textwrap
import zlib

SEED = 17017
HERE = os.path.dirname(os.path.abspath(__file__))

SYLLABLES = ["quar", "vel", "zor", "thim", "brak", "olun", "dra", "mex", "kiv", "ost", "pel", "rund",
             "sav", "tol", "ux", "yrr", "fen", "gar", "hol", "jask", "lum", "nev", "pry", "wix"]


def make_tokens(rng, n):
    toks = []
    while len(toks) < n:
        word = "".join(rng.choice(SYLLABLES) for _ in range(3)).upper()
        tok = "%s-%04d" % (word, rng.randint(1000, 9999))
        if tok not in toks:
            toks.append(tok)
    return toks


# ------------------------------------------------------------------ filler text

BANK = {
    "garden": [
        "The tomatoes along the south fence are finally setting fruit after the cool spell.",
        "I moved the compost bin closer to the shed so the path stays dry in winter.",
        "Slugs found the lettuce again; the copper tape slowed them down but did not stop them.",
        "The rain barrel filled in two days, which is enough for a week of watering.",
        "Next season I want to rotate the beans into the bed where the squash grew.",
        "Mulching the raspberries with straw kept the weeds down for most of the summer.",
        "The neighbour gave me cuttings of a purple sage that smells stronger than mine.",
        "I should sharpen the pruning shears before the apple tree needs attention.",
        "Seedlings on the windowsill are leaning toward the light, so I turn the trays daily.",
        "The soil test came back slightly acidic, which suits the blueberries well.",
    ],
    "cooking": [
        "Toasting the spices in a dry pan first made the whole dish taste deeper.",
        "The bread rose faster than expected because the kitchen was warm.",
        "Next time use less salt in the broth; the soy sauce already brings plenty.",
        "Leftover rice works better for fried rice than freshly cooked rice.",
        "The soup froze well in small jars, and each jar is one lunch.",
        "Roasting the carrots at a higher heat gave them a nice caramel edge.",
        "I wrote the oven temperature on the recipe card so I stop guessing.",
        "The dough needs a longer rest in the fridge before it is easy to roll.",
        "A squeeze of lemon at the end fixed the stew when it tasted flat.",
        "We tried a lentil curry on Thursday and everyone asked for seconds.",
    ],
    "travel": [
        "The train left on time, and the coastline view was worth the early start.",
        "Our guesthouse had a small balcony facing the old harbour.",
        "Bring a light rain jacket even when the forecast looks clear.",
        "The museum is free on the first Sunday of the month, but it gets crowded.",
        "We walked the old town in the morning before the tour groups arrived.",
        "The bus to the lighthouse runs only twice a day outside the summer season.",
        "A paper map saved us when the phone battery ran out near the ridge.",
        "Lunch at the market hall was cheap and better than the restaurant the night before.",
        "We booked the return tickets a week ahead and saved almost half the price.",
        "The hostel kitchen was tidy and had a shelf of free spices.",
    ],
    "reading": [
        "The middle chapters drag, but the ending ties the threads together nicely.",
        "I liked how the author used letters between the two sisters to move the plot.",
        "The essay collection is uneven; the piece about rivers was the strongest.",
        "I keep a list of words I had to look up while reading.",
        "The translation reads smoothly, though some jokes clearly did not survive.",
        "This is the third book this year set in a small fishing town.",
        "I gave up on the long fantasy series after the fourth volume.",
        "The biography spends too long on childhood and rushes the later years.",
        "Short chapters made it an easy book to read on the commute.",
        "I want to reread it in a year and see whether my opinion changes.",
    ],
    "meeting": [
        "We agreed to move the weekly sync to Tuesday mornings.",
        "Action item: share the draft agenda two days before the next meeting.",
        "The budget discussion was postponed until the numbers are final.",
        "Two volunteers offered to help set up the hall on Saturday.",
        "We need a better way to track who has borrowed which tools.",
        "The group voted to keep the membership fee unchanged this year.",
        "Minutes from last time were approved without changes.",
        "Someone suggested a shared calendar for room bookings.",
        "We ran out of time before the last agenda point.",
        "The next meeting will be shorter and start fifteen minutes earlier.",
    ],
    "home": [
        "The bathroom fan is noisy again; the bearing probably needs oil.",
        "I replaced the washer in the kitchen tap and the drip stopped.",
        "The radiator in the bedroom needs bleeding before the cold weather.",
        "Painting the hallway took two coats and most of a weekend.",
        "I labelled the fuse box so the next outage is less confusing.",
        "The gutter above the back door overflows during heavy rain.",
        "We moved the bookshelf to the other wall and the room feels bigger.",
        "The smoke alarm battery was changed on the first of the month.",
        "A draught excluder under the front door made a noticeable difference.",
        "The window latch in the spare room sticks and needs adjusting.",
    ],
    "bike": [
        "The chain was stretched past the wear mark, so I replaced it.",
        "Rear brake pads are worn down; order a new pair before the long ride.",
        "Tyre pressure was low after two weeks of not riding.",
        "The gears skip under load, which usually means the cable needs tension.",
        "I cleaned the drivetrain with a rag and a little degreaser.",
        "A new bell is louder than the old one and the commute feels safer.",
        "The front light mount cracked; a zip tie holds it for now.",
        "I rode the river loop in just under an hour today.",
        "The saddle height felt wrong after the service, so I lowered it a few millimetres.",
        "Pack a spare tube and tyre levers for every ride longer than an hour.",
    ],
    "fitness": [
        "Three rounds of the bodyweight circuit took about twenty minutes.",
        "My knee felt fine on the stairs today, which is good progress.",
        "Stretching after the run helps more than stretching before it.",
        "I added one more set of squats this week.",
        "Swimming laps on Friday was harder than expected after the break.",
        "Rest days matter; I felt stronger after taking two in a row.",
        "The plank hold is up to ninety seconds.",
        "Walking to work instead of taking the bus adds about six thousand steps.",
        "The yoga class focused on balance, and I wobbled a lot.",
        "Drink more water on hot days before starting the workout.",
    ],
    "language": [
        "Practised the past tense with flash cards for fifteen minutes.",
        "The conversation group meets at the library on Wednesday evenings.",
        "I keep confusing the two words for borrowing and lending.",
        "Listening to slow news broadcasts helps with pronunciation.",
        "Wrote a short diary entry and asked a friend to correct it.",
        "The verb tables finally make sense after drawing them by hand.",
        "I understood most of a film without subtitles for the first time.",
        "Numbers above one hundred are still slow for me.",
        "The textbook dialogue about ordering food was useful at the cafe.",
        "Reviewing old vocabulary every Sunday keeps it from fading.",
    ],
    "music": [
        "Practised the scale slowly with the metronome at a low tempo.",
        "The second movement is easier once the fingering is written in.",
        "Changed the guitar strings and the tone is much brighter.",
        "The choir rehearsal focused on the tricky entry in bar twelve.",
        "Recording myself showed that I rush the quiet passages.",
        "Learned a new folk tune by ear from an old recording.",
        "The piano needs tuning; the high notes sound sour.",
        "Played duets with a friend and kept time better than usual.",
        "Warm up the hands for five minutes before playing anything fast.",
        "The concert program is set, and rehearsals start next month.",
    ],
    "photo": [
        "The golden hour light on the harbour walls was perfect for photos.",
        "Shooting in the shade avoided harsh shadows on faces.",
        "I need a better way to back up the photo folders every month.",
        "The old film camera still works, but the light meter is unreliable.",
        "Cropping tighter made the bird photo much stronger.",
        "Rainy streets at night make good reflections.",
        "I printed six favourites from the summer for the hallway frames.",
        "Keep the lens cap in the same pocket every time.",
        "A slower shutter speed blurred the waterfall nicely.",
        "Sorted last year's photos into folders by month.",
    ],
    "pets": [
        "The cat has decided the sunny chair is now hers.",
        "Vet appointment for vaccinations is booked for next month.",
        "The dog learned to wait at the door before going out.",
        "New food seems to agree with him better than the old brand.",
        "Clipped the claws today with minimal complaints.",
        "The fish tank filter was cleaned and the water is clear again.",
        "She hides under the bed whenever the vacuum comes out.",
        "Long walk by the canal; he met three other dogs.",
        "Bought a scratching post and it is actually being used.",
        "The rabbit hutch needs fresh bedding twice a week in winter.",
    ],
    "hiking": [
        "The ridge trail was muddy after the storm but the views were clear.",
        "Started at the car park at eight and reached the summit by noon.",
        "Carry more water than you think on the exposed southern route.",
        "We saw deer near the edge of the beech wood.",
        "The new boots gave me a blister on the second day.",
        "The trail markers are faded past the old quarry.",
        "Packed lunch on the flat rock above the waterfall.",
        "The descent took longer than the climb because of loose stones.",
        "Fog rolled in quickly and we turned back before the last section.",
        "A walking pole made the steep parts much easier on the knees.",
    ],
    "admin": [
        "Renewed the library card; it is valid for another two years.",
        "Sorted the paper files into bills, warranties and letters.",
        "The insurance renewal letter arrived; compare offers before signing.",
        "Set a reminder to check the smoke alarms every six months.",
        "Backed up the laptop to the external drive on Sunday.",
        "Cancelled the magazine subscription we never read.",
        "The passport expires next year, so start the renewal early.",
        "Wrote down the meter readings at the end of the month.",
        "Shredded old bank statements older than seven years.",
        "Updated the emergency contact list on the fridge.",
    ],
}

FILLER_NOTES = [
    ("2023-03-02-seed-starting", "Seed starting on the windowsill", "garden"),
    ("2023-04-18-raised-bed-plan", "Raised bed plan", "garden"),
    ("2023-07-09-tomato-blight-watch", "Watching for tomato blight", "garden"),
    ("2023-09-23-garlic-planting", "Planting garlic for next year", "garden"),
    ("lentil-curry-weeknight", "Weeknight lentil curry", "cooking"),
    ("sourdough-starter-diary", "Sourdough starter diary", "cooking"),
    ("winter-soup-rotation", "Winter soup rotation", "cooking"),
    ("2023-08-12-coastal-train-trip", "Coastal train trip", "travel"),
    ("2024-04-05-old-town-weekend", "Weekend in the old town", "travel"),
    ("packing-list-short-trips", "Packing list for short trips", "travel"),
    ("2023-10-30-lighthouse-day-trip", "Day trip to the lighthouse", "travel"),
    ("reading-notes-river-essays", "Reading notes: an essay collection about rivers", "reading"),
    ("reading-notes-fishing-town-novel", "Reading notes: the fishing town novel", "reading"),
    ("words-to-look-up", "Words to look up", "reading"),
    ("2023-11-07-allotment-committee", "Allotment committee meeting", "meeting"),
    ("2024-03-12-choir-committee", "Choir committee meeting", "meeting"),
    ("2024-05-21-tool-library-meeting", "Tool library meeting", "meeting"),
    ("bathroom-fan-repair", "Bathroom fan repair", "home"),
    ("hallway-painting", "Painting the hallway", "home"),
    ("radiator-bleeding-howto", "Bleeding the radiators", "home"),
    ("2024-02-03-gutter-overflow", "Gutter overflow", "home"),
    ("bike-chain-replacement", "Replacing the bike chain", "bike"),
    ("bike-brake-pads", "Brake pad check", "bike"),
    ("river-loop-ride-log", "River loop ride log", "bike"),
    ("knee-rehab-exercises", "Knee rehab exercises", "fitness"),
    ("swimming-laps-log", "Swimming laps log", "fitness"),
    ("bodyweight-circuit", "Bodyweight circuit", "fitness"),
    ("past-tense-flashcards", "Past tense flash cards", "language"),
    ("conversation-group-notes", "Conversation group notes", "language"),
    ("scale-practice-log", "Scale practice log", "music"),
    ("choir-rehearsal-bar-twelve", "Choir rehearsal: the entry in bar twelve", "music"),
    ("folk-tune-by-ear", "Learning a folk tune by ear", "music"),
    ("harbour-golden-hour-photos", "Golden hour photos at the harbour", "photo"),
    ("photo-folder-backup-routine", "Photo folder backup routine", "photo"),
    ("film-camera-light-meter", "Film camera light meter", "photo"),
    ("cat-vet-appointment", "Vet appointment for the cat", "pets"),
    ("dog-door-training", "Teaching the dog to wait at the door", "pets"),
    ("ridge-trail-after-storm", "Ridge trail after the storm", "hiking"),
    ("beech-wood-circuit", "Beech wood circuit", "hiking"),
    ("quarry-path-markers", "Faded markers past the quarry", "hiking"),
    ("paper-files-sorting", "Sorting the paper files", "admin"),
    ("passport-renewal-checklist", "Passport renewal checklist", "admin"),
]


def filler_markdown(rng, title, cat, idx):
    sents = BANK[cat][:]
    rng.shuffle(sents)
    lines = []
    if idx % 4 == 0:
        lines += ["---", "tags: [%s, notes]" % cat, "---", ""]
    lines += ["# " + title, ""]
    n_par = rng.randint(2, 3)
    pos = 0
    for p in range(n_par):
        k = rng.randint(2, 3)
        lines.append(" ".join(sents[pos:pos + k]))
        pos += k
        lines.append("")
        if p == 0:
            lines.append("## " + rng.choice(["Notes", "Details", "What happened", "Observations"]))
            lines.append("")
    lines.append("## " + rng.choice(["To do", "Next steps", "Reminders"]))
    lines.append("")
    for s in sents[pos:pos + rng.randint(2, 4)]:
        lines.append("- " + s)
    lines.append("")
    return "\n".join(lines)


# ------------------------------------------------------------------ fact notes and PDFs

def fact_notes(T):
    return {
        "2023-05-14-meadow-beetle-survey": (
            "# Meadow survey, May\n\n"
            "Overcast with a light westerly wind. Three of us walked the north transect and the stream edge.\n\n"
            "## Findings\n\n"
            "- Counted 23 meadow brown butterflies along the north transect.\n"
            "- The orchids by the gate are in bud but not open yet.\n"
            "- Two skylarks singing over the upper field.\n\n"
            "Under the fallen alder log near the stream we found one iridescent green beetle. "
            "We logged the iridescent beetle under specimen number %s and photographed it before "
            "putting it back under the log.\n\n"
            "## Next visit\n\n"
            "- Bring the hand lens and the field guide.\n"
            "- Check the orchids again in two weeks.\n" % T[0]),
        "grandmas-plum-cake": (
            "---\ntags: [cooking, family]\n---\n\n"
            "# Grandma's plum cake\n\n"
            "Makes one round cake. Best with late summer plums that are just soft.\n\n"
            "## Ingredients\n\n"
            "- 200 g flour\n- 150 g butter\n- 120 g sugar\n- 3 eggs\n- 8 to 10 plums, halved\n\n"
            "## Method\n\n"
            "Cream the butter and sugar, beat in the eggs one at a time, then fold in the flour. "
            "Press the plum halves into the batter, cut side up.\n\n"
            "The secret is a pinch of the spice blend Grandma always called %s. She mixed it from "
            "cinnamon, cardamom and a little black pepper, and sprinkled it over the plums before baking.\n\n"
            "Bake for about 45 minutes until a skewer comes out clean.\n" % T[1]),
        "2024-01-20-book-club-planning": (
            "# Book club planning, January\n\n"
            "Eight people came, plus two who joined by phone.\n\n"
            "## Decisions\n\n"
            "We picked four books for the next season, one per month, alternating fiction and non-fiction. "
            "After a long debate we voted to call the winter reading list %s, mostly because nobody "
            "could agree on anything sensible.\n\n"
            "## Other business\n\n"
            "- Meetings stay on the third Saturday.\n"
            "- Someone will bring a second kettle.\n" % T[2]),
    }


SIBLING_NOTES = {
    "2023-06-02-meadow-follow-up": (
        "# Meadow follow-up, June\n\n"
        "Warm and sunny. The orchids by the gate are open now, about a dozen spikes.\n\n"
        "We looked under the fallen alder log again but the iridescent beetle from May was not there. "
        "Its specimen number is written in the May survey note, together with the photo.\n\n"
        "## Next steps\n\n"
        "- Ask the county recorder whether anyone else has reported the beetle.\n"
        "- Mow the path edges before the July visit.\n"),
    "autumn-baking-log": (
        "# Autumn baking log\n\n"
        "- Baked the plum cake again for the neighbours. Used Grandma's spice blend; the recipe note has the details.\n"
        "- Apple crumble with oats on top was a hit.\n"
        "- The rye loaf came out dense; try a longer proof.\n"),
    "2024-02-17-book-club-meeting": (
        "# Book club meeting, February\n\n"
        "We discussed the first book from the winter reading list. Most people liked the ending; two did not finish it.\n\n"
        "## Notes\n\n"
        "- Next month is the non-fiction pick.\n"
        "- The library can order extra copies if we ask a month ahead.\n"),
    "gull-island-trip-ideas": (
        "# Gull Island trip ideas\n\n"
        "Take the night ferry to Gull Island on a weekday when it is quieter. The departure berth is listed "
        "in the harbour timetable PDF, so check that before going down to the quay.\n\n"
        "## To pack\n\n"
        "- Warm layers for the crossing.\n"
        "- Binoculars for the seabird cliffs.\n"),
    "pottery-studio-notes": (
        "# Pottery studio notes\n\n"
        "The kiln thermocouple was replaced last week. After the repair the controller asked for the "
        "thermocouple calibration constant; it is printed on the rating plate and also given in the kiln care manual.\n\n"
        "## Glaze tests\n\n"
        "- The celadon test tiles crazed slightly.\n"
        "- Try a slower cool on the next firing.\n"),
}

PDFS = {
    "harbor-ferry-timetable-2024": ("Harbour Ferry Timetable 2024", [
        ["Harbour Ferry Timetable 2024", "",
         "This timetable covers the regular crossings from the harbour to the outer islands. "
         "Day ferries run every ninety minutes from early morning. Bicycles travel free on all crossings, "
         "but dogs must stay on a lead on the open deck.",
         "",
         "Tickets can be bought at the kiosk on the quay or on board. Season passes are available from the harbour office.",
         "",
         "Day crossings to the north islands leave from the main pier. In strong winds the first crossing may be "
         "cancelled; notices are posted at the kiosk by seven in the morning."],
        ["Evening and night services", "",
         "Evening crossings to the north islands run until nine in the evening on weekdays and until ten at weekends.",
         "",
         "The night ferry to Gull Island departs from berth {T4} at 22:40 on weekdays. It returns at 06:15 the "
         "next morning. Passengers for the night ferry should arrive at least fifteen minutes before departure.",
         "",
         "There is no night service on public holidays. Foot passengers only; vehicles are not carried at night."],
        ["Fares", "",
         "Adult single fare, child single fare and family return tickets are shown on the kiosk board. "
         "Fares change on the first of April each year.",
         "",
         "Lost property is kept at the harbour office for one month."],
    ]),
    "kiln-care-manual": ("Kiln Care Manual", [
        ["Kiln Care Manual", "",
         "Read this manual before the first firing. Keep the kiln at least half a metre away from walls and never "
         "fire it with the lid propped open unless the program asks for venting.",
         "",
         "Vacuum the elements and the floor of the kiln after every few firings. Small chips of glaze on the "
         "elements shorten their life.",
         "",
         "Check the lid hinge and the lid seal every month."],
        ["Thermocouple replacement", "",
         "The thermocouple measures the temperature inside the kiln. Replace it when firings start to run hot or "
         "cold compared with witness cones.",
         "",
         "After replacing the thermocouple the controller asks for a calibration constant. The thermocouple "
         "calibration constant printed on the rating plate of this kiln is {T5}. Enter it exactly as printed and "
         "run a test firing with witness cones.",
         "",
         "The rating plate is on the back of the control box, next to the serial number."],
        ["Troubleshooting", "",
         "If the kiln does not reach temperature, check the elements for breaks and the relay for wear. "
         "If the controller shows an error code, switch it off for one minute and try again.",
         "",
         "Never open the control box while the kiln is plugged in."],
    ]),
    "community-garden-rules": ("Community Garden Rules", [
        ["Community Garden Rules", "",
         "Plots are allocated for one year at a time. Each member keeps their plot tidy and free of perennial weeds.",
         "",
         "Hoses may be used only in the early morning or evening during dry spells. Water butts are shared.",
         "",
         "Bonfires are not allowed. Green waste goes to the shared compost bays."],
        ["Shared tools and the shed", "",
         "The shed is open from eight until dusk. Return tools clean and dry. Report broken tools to the committee.",
         "",
         "Children are welcome but must be supervised. Dogs are not allowed inside the garden."],
    ]),
    "bike-touring-checklist": ("Bike Touring Checklist", [
        ["Bike Touring Checklist", "",
         "Before a multi-day ride, check the tyres, brakes, chain and lights. Carry a spare tube, a pump, tyre "
         "levers and a small multi-tool.",
         "",
         "Pack clothes in waterproof bags. Put heavy items low in the panniers to keep the bike stable."],
        ["On the road", "",
         "Drink before you are thirsty and eat small amounts often. Plan water stops in advance on rural routes.",
         "",
         "Check the chain each evening and clean it after wet days."],
    ]),
    "neighbourhood-newsletter-spring-2024": ("Neighbourhood Newsletter, Spring 2024", [
        ["Neighbourhood Newsletter, Spring 2024", "",
         "The spring clean-up day is on the second Saturday of April. Bags and gloves will be provided at the "
         "community centre.",
         "",
         "The library is extending its opening hours on Thursdays.",
         "",
         "A new crossing is planned near the primary school."],
        ["Events", "",
         "The choir's spring concert is in the church hall. The tool library is looking for volunteers to help on "
         "Saturday mornings.",
         "",
         "The allotment open day will have plant swaps and a seed exchange."],
    ]),
}


def pdf_escape(s):
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(title, pages):
    """A minimal, valid PDF 1.4 with real text (Helvetica, WinAnsiEncoding, Flate streams)."""
    objs = []

    def add(body):
        objs.append(body)
        return len(objs)

    cat = add(None)
    pages_id = add(None)
    f1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    f2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    page_ids = []
    for page in pages:
        heading, body = page[0], page[1:]
        ops = ["BT", "/F2 15 Tf", "72 720 Td", "(%s) Tj" % pdf_escape(heading), "/F1 11 Tf", "15 TL", "T*", "T*"]
        for para in body:
            if not para:
                ops.append("T*")
                continue
            for line in textwrap.wrap(para, 86):
                ops.append("(%s) Tj" % pdf_escape(line))
                ops.append("T*")
        ops.append("ET")
        raw = ("\n".join(ops) + "\n").encode("latin-1")
        comp = zlib.compress(raw, 9)
        content = add(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(comp) + comp + b"\nendstream")
        pid = add(("<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> /Contents %d 0 R >>"
                   % (pages_id, f1, f2, content)).encode())
        page_ids.append(pid)
    objs[cat - 1] = ("<< /Type /Catalog /Pages %d 0 R >>" % pages_id).encode()
    objs[pages_id - 1] = ("<< /Type /Pages /Kids [%s] /Count %d >>"
                          % (" ".join("%d 0 R" % p for p in page_ids), len(page_ids))).encode()
    info = add(("<< /Title (%s) /Producer (q17 fixture generator) >>" % pdf_escape(title)).encode())

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n" % (len(objs) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += (b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objs) + 1, cat, info, xref))
    return bytes(out)


QUESTIONS = [
    ("q17-1", "What specimen number did we log for the iridescent beetle in the meadow survey?",
     0, "2023-05-14-meadow-beetle-survey.md"),
    ("q17-2", "What did Grandma call the spice blend that goes into the plum cake?",
     1, "grandmas-plum-cake.md"),
    ("q17-3", "What name did the book club vote to give the winter reading list?",
     2, "2024-01-20-book-club-planning.md"),
    ("q17-4", "Which berth does the night ferry to Gull Island leave from?",
     3, "harbor-ferry-timetable-2024.pdf"),
    ("q17-5", "What thermocouple calibration constant is printed on the kiln's rating plate?",
     4, "kiln-care-manual.pdf"),
]
WARMUP = "Which of my notes are about bike maintenance?"


def generate():
    rng = random.Random(SEED)
    T = make_tokens(rng, 5)
    files = {}
    for i, (stem, title, cat) in enumerate(FILLER_NOTES):
        files[stem + ".md"] = filler_markdown(rng, title, cat, i).encode("utf-8")
    for stem, text in fact_notes(T).items():
        files[stem + ".md"] = text.encode("utf-8")
    for stem, text in SIBLING_NOTES.items():
        files[stem + ".md"] = text.encode("utf-8")
    for stem, (title, pages) in PDFS.items():
        pages = [[p.replace("{T4}", T[3]).replace("{T5}", T[4]) for p in page] for page in pages]
        files[stem + ".pdf"] = build_pdf(title, pages)

    questions = {"corpus_files": len(files), "warmup_question": WARMUP, "questions": []}
    for qid, text, ti, src in QUESTIONS:
        questions["questions"].append({"id": qid, "question": text, "token": T[ti], "source_file": src,
                                       "pdf_only": src.endswith(".pdf")})
    return files, questions, T


def sanity(files, questions, T):
    names = sorted(files)
    md = [n for n in names if n.endswith(".md")]
    pdf = [n for n in names if n.endswith(".pdf")]
    assert len(md) == 50, len(md)
    assert len(pdf) == 5, len(pdf)
    stems = [os.path.splitext(n)[0] for n in names]
    for a in stems:
        for b in stems:
            if a != b:
                assert a not in b, (a, b)
    for q in questions["questions"]:
        for s in stems:
            assert s not in q["question"].lower(), (s, q["question"])
        assert q["token"] not in q["question"]
    # each token is in exactly its source file (PDF streams are checked decompressed)
    for q in questions["questions"]:
        hits = []
        for n, data in files.items():
            text = pdf_text_streams(data) if n.endswith(".pdf") else data.decode("utf-8")
            if q["token"] in text:
                hits.append(n)
        assert hits == [q["source_file"]], (q["token"], hits)
    assert len(set(T)) == 5


def pdf_text_streams(data):
    out = []
    for m in re.finditer(rb"stream\n(.*?)\nendstream", data, re.S):
        try:
            out.append(zlib.decompress(m.group(1)).decode("latin-1"))
        except zlib.error:
            pass
    return "\n".join(out)


def write(out_dir, files, questions):
    cdir = os.path.join(out_dir, "corpus")
    os.makedirs(cdir, exist_ok=True)
    for n in os.listdir(cdir):
        os.remove(os.path.join(cdir, n))
    for n, data in sorted(files.items()):
        with open(os.path.join(cdir, n), "wb") as f:
            f.write(data)
    with open(os.path.join(out_dir, "questions.json"), "w", encoding="utf-8") as f:
        json.dump(questions, f, indent=1, ensure_ascii=False)
        f.write("\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=HERE)
    a = ap.parse_args()
    files, questions, T = generate()
    sanity(files, questions, T)
    write(a.out, files, questions)
    total = sum(len(v) for v in files.values())
    print("wrote %d files (%d bytes) to %s" % (len(files), total, os.path.join(a.out, "corpus")))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Build LoRA JSONL from STABLE CSUB facts only.

Hours, calendars, prices, and other things that change stay in knowledge/
for RAG. Fine-tune examples are identity, history, campuses, and colleges.
"""

import json
import os
import random

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
SEED = 42
VALID_FRACTION = 0.12

SYSTEM = (
    'You are CSUBot, the student assistant for California State University, '
    'Bakersfield (CSUB). Answer with stable campus facts: what CSUB is, '
    'history, campuses, colleges, mascot, and similar general information. '
    'Do not invent hours, calendars, prices, or current-term dates.'
)

ABSTAIN = (
    'I do not have that personal or changing information. '
    'Please check https://www.csub.edu or the office that handles that topic.'
)


def example(questions, answer):
    rows = []
    for q in questions:
        rows.append({
            'messages': [
                {'role': 'system', 'content': SYSTEM},
                {'role': 'user', 'content': q},
                {'role': 'assistant', 'content': answer},
            ]
        })
    return rows


def all_examples():
    rows = []

    rows += example(
        [
            'what is csub',
            'what does CSUB stand for',
            'what school is this',
            'is CSUB a university',
            'tell me about csub',
            'what is California State University Bakersfield',
            'csub meaning',
            'is csub a community college',
            'is csub part of the CSU system',
        ],
        'CSUB is California State University, Bakersfield, a public university '
        'in the California State University (CSU) system in the southern San '
        'Joaquin Valley. It is the only public university within nearly 100 miles. '
        'The main campus is at 9001 Stockdale Highway, Bakersfield, CA 93311. '
        'The mascot is the Roadrunner (Rowdy), colors are blue and gold, and '
        'the motto is `Runners on the rise! It is WSCUC-accredited and a '
        'Hispanic-Serving Institution. Website: https://www.csub.edu',
    )

    rows += example(
        [
            'who is the csub mascot',
            'what is rowdy',
            'what animal is the csub mascot',
            'csub mascot name',
            'is the mascot a roadrunner',
            'why is the mascot a roadrunner',
        ],
        'The CSUB mascot is the Roadrunner, named Rowdy. Students and alumni '
        'are called Roadrunners or `Runners. The Roadrunner was chosen in 1970 '
        'from 33 nominated mascots; the idea came from a group in Buttonwillow. '
        'The final vote was Roadrunner over El Cid.',
    )

    rows += example(
        [
            'where is csub',
            'what is the csub address',
            'where is the campus located',
            'csub street address',
            'is csub in bakersfield',
            'how big is the campus',
        ],
        'The main campus is at 9001 Stockdale Highway, Bakersfield, CA 93311-1022, '
        'on about 375 acres in the southern San Joaquin Valley. CSUB also has a '
        'satellite campus in Lancaster: CSUB Antelope Valley.',
    )

    rows += example(
        [
            'when was csub founded',
            'when did csub start',
            'csub history',
            'was csub always a university',
            'what was csub original name',
        ],
        'The CSU system authorized CSUB in 1965 (the year on the university seal). '
        'It opened as California State College, Bakersfield, with first classes on '
        'October 1, 1970. It earned university status in 1987.',
    )

    rows += example(
        [
            'what colleges does csub have',
            'csub academic colleges',
            'what can I major in at csub',
            'how many colleges at csub',
        ],
        'CSUB has four colleges: Arts and Humanities; Business and Public '
        'Administration; Natural Sciences, Mathematics and Engineering; and '
        'Social Sciences and Education. It offers undergraduate and graduate '
        'programs, teaching credentials, and doctoral programs in educational '
        'leadership and nursing practice.',
    )

    rows += example(
        [
            'does csub have another campus',
            'what is csub antelope valley',
            'where is the lancaster campus',
            'csub av address',
            'csub satellite campus',
        ],
        'Yes. CSUB Antelope Valley is in Lancaster at 43909 30th Street West, '
        'on the Antelope Valley College campus. Phone: (661) 952-5000. '
        'Email: csubav@csub.edu Website: https://www.csub.edu/av/ '
        'It offers bachelor\'s, master\'s, and teacher credential programs.',
    )

    rows += example(
        [
            'what conference is csub in',
            'csub athletics',
            'are the roadrunners division 1',
            'what sports does csub have',
        ],
        'CSUB competes in NCAA Division I in the Big West Conference, with 16 '
        'teams. Men: baseball, basketball, soccer, swimming and diving, track '
        'and field, wrestling. Women: basketball, beach volleyball, cross country, '
        'golf, soccer, softball, swimming and diving, track and field, volleyball.',
    )

    rows += example(
        [
            'csub school colors',
            'what color is csub',
            'csub motto',
        ],
        'School colors are blue and gold. The motto is `Runners on the rise!',
    )

    rows += example(
        [
            'is csub accredited',
            'is csub a hispanic serving institution',
            'is csub an HSI',
        ],
        'Yes. CSUB is accredited by WSCUC (the Western Association of Schools '
        'and Colleges, Senior College and University Commission) and is a '
        'designated Hispanic-Serving Institution.',
    )

    rows += example(
        [
            'what is the csub library called',
            'who is stiern library named after',
            'name of the csub library',
        ],
        'The main library is the Walter W. Stiern Library, named for State Senator '
        'Walter W. Stiern, who helped establish the campus.',
    )

    rows += example(
        [
            'are there kit foxes on campus',
            'wildlife at csub',
        ],
        'Yes. Endangered San Joaquin kit foxes live on the Bakersfield campus. '
        'Dens can be in open areas. Foxes with collars are part of population monitoring.',
    )

    rows += example(
        [
            'what is donahoe hall',
            'who was dorothy donahoe',
        ],
        'The CSU system was created by the Donahoe Higher Education Act of 1960. '
        'Dorothy Donahoe Hall on campus is named after Assemblywoman Dorothy Donahoe '
        'of Bakersfield, who helped establish the CSU system.',
    )

    rows += example(
        [
            'csub main phone number',
            'how do I call csub',
            'csub website',
        ],
        'Main campus: (661) 654-2782 (654-CSUB). Website: https://www.csub.edu '
        'Mailing address: 9001 Stockdale Highway, Bakersfield, CA 93311-1022.',
    )

    rows += example(
        [
            'what is student life like',
            'are there clubs at csub',
            'student recreation center',
        ],
        'CSUB has a Student Recreation Center, many student clubs and organizations, '
        'NCAA Division I sports, and on-campus events. The student newspaper is The Runner.',
    )

    rows += example(
        [
            'what is the wifi password',
            'what did I get on my midterm',
            'who is teaching CS 321 next semester',
            'can you write my essay',
            'what is my student id',
        ],
        ABSTAIN,
    )

    return rows


def split_rows(rows):
    random.Random(SEED).shuffle(rows)
    n_valid = max(1, int(len(rows) * VALID_FRACTION))
    return rows[n_valid:], rows[:n_valid]


def write_jsonl(path, rows):
    with open(path, 'w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    train, valid = split_rows(all_examples())
    write_jsonl(os.path.join(DATA_DIR, 'train.jsonl'), train)
    write_jsonl(os.path.join(DATA_DIR, 'valid.jsonl'), valid)
    print(f'Wrote {len(train)} train and {len(valid)} valid examples to {DATA_DIR}')


if __name__ == '__main__':
    main()

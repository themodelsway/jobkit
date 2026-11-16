"""Shared helpers for the visual-reading tests: a fictional resume page as text, and a reading of it."""


TEXT = ("Alex Example\n\nWork Experience\nNorthwind Traders   09/2021 - Present\nSenior Engineer\n"
        "• Led migration of 40 services to Kubernetes, cutting hosting cost by 30%.\n"
        "• Designed an event-driven order pipeline handling 2 million messages a day.\n"
        "Skills: Python, Kubernetes\nEducation: BS Computer Science\n")


READING = {"employers": [{"name": "Northwind Traders", "title": "Senior Engineer", "start": "2021-09", "end": None,
                          "bullets": ["Led migration of 40 services to Kubernetes, cutting hosting cost by 30%.",
                                      "Designed an event-driven order pipeline handling 2 million messages a day."]}],
           "skills": ["Python", "Kubernetes"], "certifications": [], "education": ["BS Computer Science"], "summary": ""}

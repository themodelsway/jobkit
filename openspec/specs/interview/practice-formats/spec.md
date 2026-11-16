# interview/practice-formats Specification

## Purpose
How the interview-prep and tutor skills run and grade each kind of knowledge card, and how they adapt setup and leadership practice to the user's role.

## Requirements

### Requirement: Grade against the printed rubric
The skills SHALL tell the agent to grade a knowledge answer against the rubric that showing the card prints, never against a rubric from another track or from memory.

#### Scenario: Product card
- **WHEN** the user answers a card from a product track
- **THEN** the skill tells the agent to grade it against that track's rubric

### Requirement: Running a case
The interview-prep skill SHALL tell the agent to open a case card with its situation, to reveal further information only when the user asks for it, to push back at least once, and to grade the whole exchange when the user gives a recommendation or ends it.

#### Scenario: User asks for data
- **WHEN** during a case the user asks for a figure the situation did not give
- **THEN** the skill tells the agent to supply a plausible figure and say it is made up for practice

#### Scenario: User ends the case
- **WHEN** the user gives a recommendation
- **THEN** the skill tells the agent to grade the whole exchange against the rubric

### Requirement: Running a role-play
The interview-prep skill SHALL tell the agent to say which part it plays and what the user's goal is, to stay in that part until the user ends the role-play or reaches the goal, and then to step out and grade the exchange.

#### Scenario: Role-play ends
- **WHEN** the user says they are done
- **THEN** the skill tells the agent to step out of the part and grade the exchange against the rubric

### Requirement: Facts from approved sources
The skills SHALL tell the agent to check facts on the track's source hosts before stating or correcting them, for the track's country when it names one, and to say "unverified" when it cannot check; facts SHALL NOT come from memory.

#### Scenario: Country-specific fact
- **WHEN** a user's answer on a UK people track touches a legal notice period
- **THEN** the skill tells the agent to check it on that track's sources for the United Kingdom before correcting

### Requirement: Setup asks about the role, not only technology
The setup questions SHALL ask what kind of role the user is preparing for and what to focus on, with a technology as only one example. The skill SHALL tell the agent to choose the role family itself and to ask the user only when the role could fit more than one.

#### Scenario: Clear role
- **WHEN** the user says they are preparing for a backend engineer role
- **THEN** the skill tells the agent to use the engineering family without asking

#### Scenario: Unclear role
- **WHEN** the user says they are preparing for an operations lead role
- **THEN** the skill tells the agent to ask one question to choose between the families it could fit

#### Scenario: Seed shown before saving
- **WHEN** the agent builds a seed for a new track
- **THEN** the skill tells the agent to show its topics and rubric to the user in plain words and save it only once the user responds with yes

### Requirement: Leadership practice for roles that lead people
The skills SHALL tell the agent to offer leadership practice when the user's role or resumes involve leading people, and not to push it on other roles; the user SHALL still be able to ask for it.

#### Scenario: Individual contributor
- **WHEN** the user prepares for a frontend developer role and has never led a team
- **THEN** the skill tells the agent not to suggest leadership practice unless the user asks

### Requirement: Teaching a case or role-play
The tutor skill SHALL tell the agent to teach a case or role-play card by explaining what the interviewer looks for and walking through a short example before any practice.

#### Scenario: Learn a role-play
- **WHEN** the user asks to learn about a role-play card
- **THEN** the skill tells the agent to explain what is assessed and show a short example exchange

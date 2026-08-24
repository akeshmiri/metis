# Records — behaviour specification

Status: **Draft**

The intent side of the demo corpus. These are hand-written criteria: nobody
generated them from the code, so they can genuinely disagree with it, which is
the whole point of comparing the two.

`AC-4` disagrees with the implementation on purpose — it says `DELETE` answers
`204 No Content`, and `demo_project/openapi.json` documents `200`. Two stated
sources, one implementation, and a deviation a person has to settle.

## Reading a record

### AC-1: A known record is returned

**Given** a record exists with id `r-1`
**When** the client sends `GET /record/r-1`
**Then** the response is `200 OK` and carries the record

### AC-2: An unknown record is refused, not empty

**Given** no record exists with id `missing`
**When** the client sends `GET /record/missing`
**Then** the response is `404 Not Found` and carries an error code

## Creating a record

### AC-3: A titled record is created

**Given** a request body with a non-empty title and an owner
**When** the client sends `POST /record`
**Then** the response is `201 Created` and carries the stored record

### AC-3b: A blank title is refused

**Given** a request body whose title is blank
**When** the client sends `POST /record`
**Then** the response is `400 Bad Request` and no record is stored

## Deleting a record

### AC-4: Deletion answers with no body

**Given** a record exists with id `r-1`
**When** the client sends `DELETE /record/r-1`
**Then** the response is `204 No Content` and carries no body

## Archiving

### AC-5: Archiving is accepted for later work

**Given** a record exists with id `r-1`
**When** the client sends `POST /record/r-1/archive`
**Then** the response is `202 Accepted`

### AC-6: Archiving a locked record is refused

**Given** the record with id `r-1` is locked
**When** the client sends `POST /record/r-1/archive`
**Then** the request is refused and the reason names the lock

## Not a transition

### AC-7: Every refusal carries a stable machine-readable code

A narrative criterion. It constrains every rejection rather than describing one
interaction, so it is not a transition and must be returned marked rather than
forced into a Given/When/Then it does not have.

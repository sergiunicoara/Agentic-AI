A support ticket came in saying that looking up a specific member by id sometimes
throws an unhandled error and the request fails hard instead of giving a normal
"member not found" response. It only happens for ids that don't exist in the
current roster -- looking up ids that do exist works fine. The error in the logs
was `IndexError: list index out of range`.

Got a crash report from someone who'd just created a new quiz and hadn't had anyone
take it yet. Stack trace points into the stats helper somewhere, ZeroDivisionError. My
guess is it's trying to average scores before any exist.

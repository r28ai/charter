# Voided: the first run of the tool_filter arm

Recorded 2026-10-24 and kept so the record is complete. AgentDojo's tool filter asks
its model, with `tool_choice="none"`, which tools the task needs. Fireworks does not
show a model its tools under `"none"`, so the model named tools that do not exist,
the filter removed nearly every tool, and each task either always passed or always
failed, identically on both models. That measured the provider, not the defense.
`run.py`'s `VisibleToolFilter` lists the tools in the filter's prompt, and the arm
was run again.

# Voided: the second run of the tool_filter arm

With the tools listed, the filter chose sensibly, but it leaves its own reply as the
last message of the conversation, and Fireworks answers that with an empty message:
the agent never started. `VisibleToolFilter` now drops the filter's exchange once it
has chosen, and the arm was run a third time.

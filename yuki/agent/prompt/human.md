[Begin of Agent State]
    Steps: {steps}/{max_steps}
[End of Agent State]
{loop_warning}
[Begin of Desktop]
    Cursor Location: {cursor_location}
    
    [Begin of Window Info]
        Foreground Window: {active_window}
    
        Background Windows:
        {windows}
    [End of Window Info]
    
    [Begin of Screen]
        {ax_warning}List of Interactive Elements:
        {interactive_elements}

        List of Scrollable Elements:
        {scrollable_elements}

        Visible Text (what the screen says, reading order):
        {visible_text}
    [End of Screen]
[End of Desktop]

{ui_change}

[Begin of User Query]
    {query}
[End of User Query]

REMINDER: You MUST use `done_tool` to deliver any response to the user. Do not produce a text-only reply.
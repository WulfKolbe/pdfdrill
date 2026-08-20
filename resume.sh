printf '\033]2;%s\007' 'iPDFDRILL'
printf '\033]1;%s\007' 'PDFDRILL'
export CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1

#!/bin/bash
claude --resume ae99387a-8fcf-4b96-b9d9-5dc00cc6f8da --dangerously-skip-permissions


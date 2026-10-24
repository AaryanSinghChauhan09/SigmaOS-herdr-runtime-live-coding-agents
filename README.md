    # SigmaOS-herdr-runtime-live-coding-agents

    Live-coding agent runtime (herdr)

    Part of the **SigmaOS** sovereign operating-system ecosystem — a multi-repository
    distribution modelled on Linux Mint and Omarchy Linux. See the parent
    [`SigmaOS`](https://github.com/AaryanSinghChauhan09/SigmaOS) repository for the
    full component index.

    ## Upstream inspirations
    - https://github.com/omacom/herdr

    ## Design principles applied
    - **Separation of Concerns**
- **Defensive Programming**
- **Fail-Fast**
- **Least Astonishment**
- **KISS**
- **Deterministic Testing**

    ## Usage
    Verbs: `spawn-plan, session, tools, stop-plan`

    ```
    $ sigma-herdr spawn-plan --agent claude --session webapp --cwd ~/src/webapp --mux tmux
$ sigma-herdr session sessions.json
$ sigma-herdr tools --profile read-only
$ sigma-herdr tools --profile standard --config
$ sigma-herdr stop-plan --session webapp --pid 4242 --grace 5

    ```

    ## Build & test
    ```
    make build
    make test
    ```

    ## Licence
    GNU General Public License v3.0 (FOSS).

/**
 * AnsiTerminalBuffer - Virtual terminal buffer for handling ANSI cursor movement codes
 *
 * This class implements a character-based virtual terminal buffer that tracks cursor
 * position and handles ANSI escape sequences for cursor movement and line clearing.
 * It works in tandem with ansi_up for color handling.
 */
class AnsiTerminalBuffer {
    constructor() {
        this.buffer = [];        // Array<Array<{char: string, ansi: string}>>
        this.cursorRow = 0;
        this.cursorCol = 0;
        this.currentAnsi = '';   // Track current ANSI formatting state
    }

    /**
     * Main entry point: process text with ANSI codes
     */
    write(text) {
        const parts = this._parseAnsiText(text);

        for (const part of parts) {
            if (part.type === 'escape') {
                this._handleEscapeCode(part.code);
            } else if (part.type === 'text') {
                this._writeText(part.text);
            }
        }
    }

    /**
     * Parse text into chunks of text and escape codes
     * Returns array of {type: 'text'|'escape', content: string}
     */
    _parseAnsiText(text) {
        const parts = [];
        // Match cursor movement, line clearing, and SGR (color/formatting) codes
        const escapePattern = /\x1b\[([^m]*m|\d*[ABCD]|[012]?K)/g;
        let lastIndex = 0;
        let match;

        while ((match = escapePattern.exec(text)) !== null) {
            // Add text before this escape code
            if (match.index > lastIndex) {
                parts.push({
                    type: 'text',
                    text: text.substring(lastIndex, match.index)
                });
            }

            // Add the escape code
            parts.push({
                type: 'escape',
                code: match[0]
            });

            lastIndex = match.index + match[0].length;
        }

        // Add remaining text
        if (lastIndex < text.length) {
            parts.push({
                type: 'text',
                text: text.substring(lastIndex)
            });
        }

        return parts;
    }

    /**
     * Parse and execute ANSI escape sequences
     */
    _handleEscapeCode(code) {
        // Cursor movement codes
        if (code.match(/\x1b\[(\d*)A/)) {
            // Cursor up
            const n = parseInt(RegExp.$1) || 1;
            this.cursorRow = Math.max(0, this.cursorRow - n);
        } else if (code.match(/\x1b\[(\d*)B/)) {
            // Cursor down
            const n = parseInt(RegExp.$1) || 1;
            this.cursorRow = this.cursorRow + n;
            this._ensureRow(this.cursorRow);
        } else if (code.match(/\x1b\[(\d*)C/)) {
            // Cursor forward (right)
            const n = parseInt(RegExp.$1) || 1;
            this.cursorCol = this.cursorCol + n;
        } else if (code.match(/\x1b\[(\d*)D/)) {
            // Cursor backward (left)
            const n = parseInt(RegExp.$1) || 1;
            this.cursorCol = Math.max(0, this.cursorCol - n);
        } else if (code.match(/\x1b\[([012]?)K/)) {
            // Clear line
            const mode = RegExp.$1 || '0';
            this._clearLine(mode);
        } else if (code.match(/\x1b\[[^m]*m/)) {
            // Color/formatting code - store for later use
            this.currentAnsi = code;
        }
    }

    /**
     * Write text at current cursor position with current formatting
     */
    _writeText(text) {
        for (const char of text) {
            if (char === '\n') {
                this.cursorRow++;
                this.cursorCol = 0;
                this._ensureRow(this.cursorRow);
            } else if (char === '\r') {
                this.cursorCol = 0;
            } else {
                // Ensure row exists
                this._ensureRow(this.cursorRow);
                // Ensure column exists (pad with spaces if needed)
                while (this.buffer[this.cursorRow].length <= this.cursorCol) {
                    this.buffer[this.cursorRow].push({char: ' ', ansi: ''});
                }
                // Write character with current formatting
                this.buffer[this.cursorRow][this.cursorCol] = {
                    char: char,
                    ansi: this.currentAnsi
                };
                this.cursorCol++;
            }
        }
    }

    /**
     * Auto-expand buffer to accommodate the specified row
     */
    _ensureRow(row) {
        while (this.buffer.length <= row) {
            this.buffer.push([]);
        }
    }

    /**
     * Clear line based on mode
     * mode '0' or '' - Clear from cursor to end of line
     * mode '1' - Clear from beginning to cursor
     * mode '2' - Clear entire line
     */
    _clearLine(mode) {
        this._ensureRow(this.cursorRow);
        const row = this.buffer[this.cursorRow];

        if (mode === '0' || mode === '') {
            // Clear from cursor to end of line
            row.splice(this.cursorCol);
        } else if (mode === '1') {
            // Clear from beginning to cursor
            for (let i = 0; i <= this.cursorCol && i < row.length; i++) {
                row[i] = {char: ' ', ansi: ''};
            }
        } else if (mode === '2') {
            // Clear entire line
            this.buffer[this.cursorRow] = [];
            this.cursorCol = 0;
        }
    }

    /**
     * Convert buffer to text with ANSI codes for ansi_up processing
     * Optimizes by only emitting ANSI codes when formatting changes
     */
    renderToText() {
        let result = '';
        let lastAnsi = '';

        for (const row of this.buffer) {
            for (const cell of row) {
                // Only emit ANSI code if it changed
                if (cell.ansi !== lastAnsi) {
                    // When transitioning to no-color, emit explicit reset
                    // to prevent color bleeding across rows
                    if (cell.ansi === '' && lastAnsi !== '') {
                        result += '\x1b[0m';
                    } else {
                        result += cell.ansi;
                    }
                    lastAnsi = cell.ansi;
                }
                result += cell.char;
            }
            // Reset color at end of row to prevent bleeding across rows
            if (lastAnsi !== '') {
                result += '\x1b[0m';
                lastAnsi = '';
            }
            result += '\n';
        }

        return result;
    }

    /**
     * Clear the entire buffer and reset cursor position
     */
    clear() {
        this.buffer = [];
        this.cursorRow = 0;
        this.cursorCol = 0;
        this.currentAnsi = '';
    }
}

class QuenchClient {
    constructor() {
        this.ws = null;
        this.kernelId = null;
        this.cells = new Map(); // Map from msg_id to cell element
        this.outputArea = null;
        this.kernelSelect = null;
        this.kernelCountContainer = null;
        this.kernelCount = null;
        this.kernelInfoToggle = null;
        this.kernelInfoDropdown = null;
        this.kernelDetails = {}; // Store detailed kernel information
        this.ansiUp = new AnsiUp(); // ANSI code converter
        this.autoscrollButton = null; // Reference to autoscroll toggle button
        this.isAutoscrollEnabled = true; // Track autoscroll state
        this.scrollThreshold = 100; // Pixels from bottom to consider "at bottom"
        this.isProgrammaticScroll = false; // Track programmatic scrolls to ignore them
        this.userScrollTimer = null; // Debounce timer for user scroll end detection
        this.isUserScrolling = false; // Track active user scrolling state
        this.isKernelDataLoaded = false; // Track if kernel data is loaded
        this.loadingTimeout = null; // Timeout for loading fallback
        this.pollingIntervalId = null; // Interval ID for kernel polling
        this.lastKernelIds = null; // Track kernel IDs to prevent redundant updates

        // State machine properties for reactive kernel status
        this.connectionState = 'disconnected';
        this.errorTimeout = null; // To manage error flash persistence

        // Buffers for messages that arrive out of order
        this.pendingStatuses = new Map();  // Buffered status updates
        this.pendingOutputs = new Map();   // Buffered output messages

        this.init();
    }

    init() {
        // Get DOM elements
        this.outputArea = document.getElementById('output-area');
        this.kernelSelect = document.getElementById('kernel-select');
        this.kernelCountContainer = document.getElementById('kernel-count-container');
        this.kernelCount = document.getElementById('kernel-count');
        this.kernelInfoToggle = document.getElementById('kernel-info-toggle');
        this.kernelInfoDropdown = document.getElementById('kernel-info-dropdown');
        this.autoscrollButton = document.getElementById('autoscroll-toggle');

        // Set up event handlers
        this.kernelSelect.addEventListener('change', () => this.onKernelSelected());
        this.kernelSelect.addEventListener('mousedown', (e) => this.handleDropdownClick(e));
        this.kernelInfoToggle.addEventListener('click', () => this.toggleKernelInfoDropdown());
        this.autoscrollButton.addEventListener('click', () => this.toggleAutoscroll());
        this.updateAutoscrollButton();
        this.setupScrollHandling();
        
        // Close dropdown when clicking outside
        document.addEventListener('click', (event) => {
            if (!this.kernelInfoToggle.contains(event.target) &&
                !this.kernelInfoDropdown.contains(event.target) &&
                !this.kernelInfoDropdown.classList.contains('hidden')) {
                this.kernelInfoDropdown.classList.add('hidden');
            }
        });
        
        // Load available kernels on startup
        this.loadKernels();

        // Start periodic polling for kernel list
        this.startKernelPolling();

        // Also check URL for kernel_id (backward compatibility)
        const urlKernelId = this.getKernelIdFromUrl();
        if (urlKernelId) {
            setTimeout(() => this.selectKernel(urlKernelId), 500);
        }
    }

    startKernelPolling() {
        // Clear any existing polling interval
        this.stopKernelPolling();

        // Poll every 1 second
        this.pollingIntervalId = setInterval(() => {
            this.loadKernels();
        }, 1000);
    }

    stopKernelPolling() {
        if (this.pollingIntervalId) {
            clearInterval(this.pollingIntervalId);
            this.pollingIntervalId = null;
        }
    }

    setupScrollHandling() {
        // Listen to scroll events to detect when user scrolls away from bottom
        window.addEventListener('scroll', () => {
            // Ignore our own programmatic scrolls
            if (this.isProgrammaticScroll) {
                return;
            }

            // Mark that user is actively scrolling
            this.isUserScrolling = true;

            // Clear existing timer
            if (this.userScrollTimer) {
                clearTimeout(this.userScrollTimer);
            }

            // Wait for user to finish scrolling (150ms debounce)
            this.userScrollTimer = setTimeout(() => {
                this.isUserScrolling = false;

                // Check final position after user stops scrolling
                const scrollHeight = document.documentElement.scrollHeight;
                const scrollTop = window.scrollY || document.documentElement.scrollTop;
                const clientHeight = window.innerHeight;
                const distanceFromBottom = scrollHeight - (scrollTop + clientHeight);

                const isAtBottom = distanceFromBottom <= this.scrollThreshold;

                if (isAtBottom && !this.isAutoscrollEnabled) {
                    // User scrolled back to bottom - re-enable autoscroll
                    this.isAutoscrollEnabled = true;
                    this.updateAutoscrollButton();
                } else if (!isAtBottom && this.isAutoscrollEnabled) {
                    // User scrolled away from bottom - disable autoscroll
                    this.isAutoscrollEnabled = false;
                    this.updateAutoscrollButton();
                }
            }, 150);
        }, { passive: true });
    }

    handleDropdownClick(e) {
        if (!this.isKernelDataLoaded) {
            // Prevent dropdown from opening until data is loaded
            e.preventDefault();

            // Start loading kernels
            this.loadKernels();

            // Set timeout for fallback message
            if (this.loadingTimeout) {
                clearTimeout(this.loadingTimeout);
            }

            this.loadingTimeout = setTimeout(() => {
                if (!this.isKernelDataLoaded) {
                    this.kernelSelect.innerHTML = '<option value="">Loading kernels is taking longer than expected...</option>';
                    // Allow dropdown to open now
                    this.kernelSelect.size = 0; // Reset size to allow normal dropdown
                }
            }, 3000); // 3 second timeout
        } else {
            // Data is loaded, refresh it
            this.loadKernels();
        }
    }

    async loadKernels() {
        try {
            // Set loading state without changing dropdown content if not already loading
            const wasLoading = this.kernelSelect.innerHTML.includes('Loading kernels...');
            if (!wasLoading && !this.isKernelDataLoaded) {
                this.kernelSelect.innerHTML = '<option value="">Loading kernels...</option>';
            }

            const response = await fetch('/api/sessions');
            const data = await response.json();

            // Clear any loading timeout
            if (this.loadingTimeout) {
                clearTimeout(this.loadingTimeout);
                this.loadingTimeout = null;
            }

            const sessions = data.sessions || {};
            const sessionCount = Object.keys(sessions).length;
            const currentKernelIds = Object.keys(sessions).sort().join(',');

            // Check if kernel list has changed to prevent redundant DOM updates
            if (this.lastKernelIds === currentKernelIds && this.isKernelDataLoaded) {
                // Only update the count display, skip dropdown rebuild
                if (this.kernelCount) {
                    this.kernelCount.textContent = sessionCount;
                    if (this.kernelCountContainer) {
                        this.kernelCountContainer.style.display = sessionCount > 0 ? 'inline-block' : 'none';
                    }
                }
                return;
            }

            // Store the current kernel IDs for future comparison
            this.lastKernelIds = currentKernelIds;

            // Remember currently selected kernel to restore after rebuild
            const previouslySelectedKernelId = this.kernelSelect.value;

            this.kernelSelect.innerHTML = '<option value="">Select a kernel...</option>';

            // Update the kernel count display
            if (this.kernelCount) {
                this.kernelCount.textContent = sessionCount;
                if (this.kernelCountContainer) {
                    this.kernelCountContainer.style.display = sessionCount > 0 ? 'inline-block' : 'none';
                }
            }

            if (sessionCount > 0) {
                // Store detailed kernel information
                this.kernelDetails = sessions;

                Object.values(sessions).forEach(session => {
                    const option = document.createElement('option');
                    option.value = session.kernel_id;
                    const bufferCount = session.associated_buffers.length;
                    option.textContent = `${session.kernel_name} (${session.short_id}) - ${bufferCount} buffer${bufferCount !== 1 ? 's' : ''}`;
                    this.kernelSelect.appendChild(option);
                });

                // Restore previous selection if it still exists
                if (previouslySelectedKernelId && sessions[previouslySelectedKernelId]) {
                    this.kernelSelect.value = previouslySelectedKernelId;
                }
                // Auto-select if only one kernel and none currently selected/connected
                else if (sessionCount === 1 && !this.kernelId) {
                    const singleKernelId = Object.keys(sessions)[0];
                    this.kernelSelect.value = singleKernelId;
                    this.onKernelSelected();
                }
            } else {
                const option = document.createElement('option');
                option.value = '';
                option.textContent = 'No kernels available - run :QuenchRunCell in Neovim';
                this.kernelSelect.appendChild(option);
            }

            // Mark data as loaded
            this.isKernelDataLoaded = true;
        } catch (error) {
            console.error('Failed to load kernels:', error);
            this.kernelSelect.innerHTML = '<option value="">Error loading kernels</option>';
            this.isKernelDataLoaded = true; // Mark as "loaded" to prevent endless retries

            // Clear any loading timeout
            if (this.loadingTimeout) {
                clearTimeout(this.loadingTimeout);
                this.loadingTimeout = null;
            }
        }
    }

    selectKernel(kernelId) {
        this.kernelSelect.value = kernelId;
        this.onKernelSelected();
    }

    onKernelSelected() {
        const selectedKernelId = this.kernelSelect.value;

        if (!selectedKernelId) {
            this.disconnect();
            this.setKernelState('disconnected');
            this.updateKernelInfoDropdown(null);
            return;
        }

        if (selectedKernelId !== this.kernelId) {
            this.kernelId = selectedKernelId;
            this.updateKernelInfoDropdown(selectedKernelId);
            this.clearOutput();
            this.connect();
        }
    }

    getKernelIdFromUrl() {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get('kernel_id');
    }

    connect() {
        if (!this.kernelId) {
            this.setKernelState('disconnected');
            return;
        }

        // Close existing connection
        this.disconnect();

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/${this.kernelId}`;

        console.log(`Connecting to WebSocket: ${wsUrl}`);
        this.setKernelState('connecting');

        try {
            this.ws = new WebSocket(wsUrl);
            this.setupWebSocketHandlers();
        } catch (error) {
            console.error('Failed to create WebSocket connection:', error);
            this.setKernelState('disconnected');
        }
    }

    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }

    clearOutput() {
        // Clear all cells except header
        const cells = this.outputArea.querySelectorAll('.cell');
        cells.forEach(cell => cell.remove());
        this.cells.clear();
    }

    setupWebSocketHandlers() {
        this.ws.onopen = (event) => {
            console.log('WebSocket connection opened');
            // Start in connecting state - will transition to idle/busy as kernel reports status
            this.setKernelState('connecting');
        };

        this.ws.onmessage = (event) => {
            console.log('Raw WebSocket message received:', event.data);
            try {
                const message = JSON.parse(event.data);
                console.log('Parsed WebSocket message:', message);
                this.handleMessage(message);
            } catch (error) {
                console.error('Failed to parse WebSocket message:', error, event.data);
            }
        };

        this.ws.onclose = (event) => {
            console.log('WebSocket connection closed:', event.code, event.reason);
            this.setKernelState('disconnected');
        };

        this.ws.onerror = (event) => {
            console.error('WebSocket error:', event);
            this.setKernelState('disconnected');
        };
    }

    handleMessage(message) {
        const msgType = message.msg_type;
        const msgId = message.header?.msg_id;
        const parentMsgId = message.parent_header?.msg_id;
        
        console.log(`Received message: ${msgType} (msg_id: ${msgId?.slice(0,8)}, parent: ${parentMsgId?.slice(0,8)})`);
        
        switch (msgType) {
            case 'execute_input':
                console.log('Processing execute_input message');
                this.handleExecuteInput(message);
                break;
                
            case 'stream':
                console.log('Processing stream message, current cells:', Array.from(this.cells.keys()).map(k => k.slice(0,8)));
                this.handleStream(message);
                break;
                
            case 'display_data':
            case 'execute_result':
                this.handleDisplayData(message);
                break;
                
            case 'error':
                this.handleError(message);
                break;
                
            case 'status':
                this.handleStatus(message);
                break;
                
            case 'kernel_restarted':
                this.handleKernelRestarted(message);
                break;

            case 'kernel_auto_restarted':
                this.handleKernelAutoRestarted(message);
                break;

            case 'kernel_died':
                this.handleKernelDied(message);
                break;

            case 'quench_cell_status':
                this.handleCellStatus(message);
                break;

            case 'kernel_update':
                console.log('Kernel update received, reloading kernel list.');
                this.loadKernels();
                break;

            default:
                console.log(`Unhandled message type: ${msgType}`);
        }
    }

    /**
     * Cell state machine with transition validation and sequence ordering.
     *
     * State transitions:
     *   queued → running, skipped
     *   running → completed_ok, completed_error, skipped
     *   completed_ok, completed_error, skipped → (TERMINAL)
     */
    setCellState(cellId, newState, sequence) {
        const cell = this.cells.get(cellId);
        if (!cell) {
            console.warn(`setCellState: Cell ${cellId.slice(0,8)} not found`);
            return false;
        }

        // Get current state from cell data attribute
        const currentState = cell.dataset.cellState || 'queued';
        const currentSequence = parseInt(cell.dataset.cellSequence || '0', 10);

        // Validate sequence number (reject old messages)
        if (sequence !== undefined && sequence < currentSequence) {
            console.warn(
                `[State Machine] Rejecting old message for ${cellId.slice(0,8)}: ` +
                `sequence ${sequence} < current ${currentSequence} ` +
                `(current state: ${currentState}, attempted: ${newState})`
            );
            return false;
        }

        // Terminal states cannot be exited
        const terminalStates = ['completed_ok', 'completed_error', 'skipped'];
        if (terminalStates.includes(currentState)) {
            console.warn(
                `[State Machine] Invalid transition for ${cellId.slice(0,8)}: ` +
                `Cannot exit terminal state "${currentState}" to "${newState}" ` +
                `(sequence: ${sequence})`
            );
            return false;
        }

        // Define valid transitions
        const validTransitions = {
            'queued': ['running', 'skipped'],
            'running': ['completed_ok', 'completed_error', 'skipped']
        };

        // Check if transition is valid
        const allowedNextStates = validTransitions[currentState] || [];
        if (!allowedNextStates.includes(newState)) {
            console.warn(
                `[State Machine] Invalid transition for ${cellId.slice(0,8)}: ` +
                `"${currentState}" → "${newState}" not allowed ` +
                `(valid: [${allowedNextStates.join(', ')}], sequence: ${sequence})`
            );
            return false;
        }

        // Valid transition - update state
        cell.dataset.cellState = newState;
        if (sequence !== undefined) {
            cell.dataset.cellSequence = sequence.toString();
        }

        // Update sidebar CSS
        const sidebar = cell.querySelector('.cell-sidebar');
        if (sidebar) {
            // Replace status class
            sidebar.className = sidebar.className.replace(/status-\w+(-\w+)?/g, '');
            sidebar.className = sidebar.className.trim() + ` status-${newState.replace(/_/g, '-')}`;

            console.log(
                `[State Machine] ${cellId.slice(0,8)}: ${currentState} → ${newState} ` +
                `(sequence: ${sequence})`
            );
        }

        return true;
    }

    handleExecuteInput(message) {
        const msgId = message.header.msg_id;
        const parentMsgId = message.parent_header?.msg_id;
        const code = message.content?.code || '';

        console.log(`Execute input: msg_id=${msgId?.slice(0,8)}, parent=${parentMsgId?.slice(0,8)}, code length=${code.length}`);

        if (!parentMsgId) {
            console.warn('Execute input message without parent_header.msg_id:', message);
            return;
        }

        // Check if cell already exists (shouldn't happen, but handle gracefully)
        if (this.cells.has(parentMsgId)) {
            console.log(`Cell ${parentMsgId.slice(0,8)} already exists, skipping creation`);
            return;
        }

        console.log(`Creating cell with ID: ${parentMsgId.slice(0,8)}`);
        const cellElement = this.createCell(parentMsgId, code);

        // Initialize state machine properties
        cellElement.dataset.cellState = 'queued';  // Initialize state
        cellElement.dataset.cellSequence = '0';    // Initialize sequence

        // Add to cells map and DOM
        this.cells.set(parentMsgId, cellElement);
        this.outputArea.appendChild(cellElement);

        console.log(`Cell created, total cells: ${this.cells.size}`);

        // Check for buffered status update
        if (this.pendingStatuses && this.pendingStatuses.has(parentMsgId)) {
            const buffered = this.pendingStatuses.get(parentMsgId);
            console.log(`Applying buffered status for ${parentMsgId.slice(0,8)}: ${buffered.status}`);
            this.setCellState(parentMsgId, buffered.status, buffered.sequence);
            this.pendingStatuses.delete(parentMsgId);
        }

        // Flush any buffered outputs that arrived before cell was created
        if (this.pendingOutputs && this.pendingOutputs.has(parentMsgId)) {
            const bufferedOutputs = this.pendingOutputs.get(parentMsgId);
            console.log(`Flushing ${bufferedOutputs.length} buffered outputs for ${parentMsgId.slice(0,8)}`);

            for (const bufferedMsg of bufferedOutputs) {
                // Re-dispatch buffered message now that cell exists
                if (bufferedMsg.msg_type === 'stream') {
                    this.handleStream(bufferedMsg);
                } else if (bufferedMsg.msg_type === 'display_data' || bufferedMsg.msg_type === 'execute_result') {
                    this.handleDisplayData(bufferedMsg);
                } else if (bufferedMsg.msg_type === 'error') {
                    this.handleError(bufferedMsg);
                }
            }

            this.pendingOutputs.delete(parentMsgId);
        }

        // Auto-scroll to bottom if enabled
        this.autoscroll();
    }

    handleStream(message) {
        const parentMsgId = message.parent_header?.msg_id;
        if (!parentMsgId) {
            console.warn('Stream message without parent_header.msg_id:', message);
            return;
        }

        // Buffer output if cell doesn't exist yet
        if (!this.cells.has(parentMsgId)) {
            console.warn(`Stream output arrived before cell ${parentMsgId.slice(0,8)}, buffering...`);

            if (!this.pendingOutputs.has(parentMsgId)) {
                this.pendingOutputs.set(parentMsgId, []);
            }
            this.pendingOutputs.get(parentMsgId).push(message);
            return;
        }

        const cell = this.cells.get(parentMsgId);
        const outputDiv = cell.querySelector('.cell-output');

        const streamName = message.content?.name || 'stdout';
        let text = message.content?.text || '';

        // FIX: Normalize CRLF (\r\n) to LF (\n).
        // Shell commands often output \r\n which triggers the \r overwrite logic
        // destructively. We only want \r logic for isolated carriage returns.
        text = text.replace(/\r\n/g, '\n');

        // Only append to the last element if it's a matching stream block.
        // This ensures that if a plot or other output type was displayed between
        // print statements, new text appears below the plot rather than jumping
        // back up to a previous text block.
        const lastChild = outputDiv.lastElementChild;
        let streamDiv = null;

        // Check if we can append to the immediately preceding element
        if (lastChild &&
            lastChild.classList.contains('output-text') &&
            lastChild.getAttribute('data-stream') === streamName) {
            streamDiv = lastChild;
        }

        if (!streamDiv) {
            // Create a new stream block
            streamDiv = document.createElement('div');
            streamDiv.className = 'output-item output-text';
            streamDiv.setAttribute('data-stream', streamName);

            const metadata = document.createElement('div');
            metadata.className = 'output-metadata';
            metadata.textContent = `${streamName}:`;
            streamDiv.appendChild(metadata);

            const textDiv = document.createElement('pre');
            textDiv.className = 'output-text';
            streamDiv.appendChild(textDiv);

            outputDiv.appendChild(streamDiv);

            // Create terminal buffer for this stream
            streamDiv._terminalBuffer = new AnsiTerminalBuffer();
        }

        const textDiv = streamDiv.querySelector('.output-text');

        // Get or create terminal buffer for this stream
        if (!streamDiv._terminalBuffer) {
            streamDiv._terminalBuffer = new AnsiTerminalBuffer();
        }
        const terminalBuffer = streamDiv._terminalBuffer;

        // Unified handling: ALL text goes through the terminal buffer
        // This handles \r, cursor movement codes, and regular text uniformly
        terminalBuffer.write(text);
        const renderedText = terminalBuffer.renderToText();
        textDiv.innerHTML = this.ansiUp.ansi_to_html(renderedText);
        
        // Auto-scroll to bottom if enabled
        this.autoscroll();
    }

    handleDisplayData(message) {
        const parentMsgId = message.parent_header?.msg_id;
        if (!parentMsgId) {
            console.warn('Display data message without parent_header.msg_id:', message);
            return;
        }

        // Buffer output if cell doesn't exist yet
        if (!this.cells.has(parentMsgId)) {
            console.warn(`Display data arrived before cell ${parentMsgId.slice(0,8)}, buffering...`);

            if (!this.pendingOutputs.has(parentMsgId)) {
                this.pendingOutputs.set(parentMsgId, []);
            }
            this.pendingOutputs.get(parentMsgId).push(message);
            return;
        }
        
        const cell = this.cells.get(parentMsgId);
        const outputDiv = cell.querySelector('.cell-output');
        
        const data = message.content?.data || {};
        const metadata = message.content?.metadata || {};
        
        // Render different MIME types
        this.renderMimeData(outputDiv, data, metadata);
        
        // Auto-scroll to bottom if enabled
        this.autoscroll();
    }

    handleError(message) {
        const parentMsgId = message.parent_header?.msg_id;
        if (!parentMsgId) {
            console.warn('Error message without parent_header.msg_id:', message);
            return;
        }

        // Buffer output if cell doesn't exist yet
        if (!this.cells.has(parentMsgId)) {
            console.warn(`Error message arrived before cell ${parentMsgId.slice(0,8)}, buffering...`);

            if (!this.pendingOutputs.has(parentMsgId)) {
                this.pendingOutputs.set(parentMsgId, []);
            }
            this.pendingOutputs.get(parentMsgId).push(message);
            return;
        }

        const cell = this.cells.get(parentMsgId);
        const outputDiv = cell.querySelector('.cell-output');

        const errorDiv = document.createElement('div');
        errorDiv.className = 'output-item output-error';

        const errorName = message.content?.ename || 'Error';
        const errorValue = message.content?.evalue || '';
        const traceback = message.content?.traceback || [];

        // Clean up ANSI escape codes from traceback
        const cleanTraceback = traceback.map(line => this.ansiUp.ansi_to_html(line));
        const errorText = `${errorName}: ${errorValue}\n${cleanTraceback.join('\n')}`;

        const errorPre = document.createElement('pre');
        errorPre.className = 'output-text';
        errorPre.innerHTML = errorText;
        errorDiv.appendChild(errorPre);

        outputDiv.appendChild(errorDiv);

        // Update kernel state to error with persistence logic
        this.setKernelState('error');

        // Set a timeout to automatically transition back to idle after 3 seconds
        // This ensures the error indicator is visible long enough for the user to notice
        this.errorTimeout = setTimeout(() => {
            // Only transition to idle if we're still in error state
            // (user might have triggered another action in the meantime)
            if (this.connectionState === 'error') {
                this.setKernelState('idle');
            }
        }, 3000); // 3 second persistence

        // Auto-scroll to bottom if enabled
        this.autoscroll();
    }

    handleStatus(message) {
        const executionState = message.content?.execution_state;
        if (executionState) {
            console.log(`Kernel execution state: ${executionState}`);

            // Guard clause: If kernel is dead, ignore status messages (zombie prevention)
            if (this.connectionState === 'dead') {
                console.log('Ignoring status message - kernel is dead');
                return;
            }

            // Guard clause: If we're in error state, ignore idle messages briefly
            // This prevents the error indicator from being cleared too quickly
            if (this.connectionState === 'error' && executionState === 'idle') {
                console.log('Ignoring idle message - still showing error');
                return;
            }

            // Map execution states to our state machine states
            switch (executionState) {
                case 'starting':
                    this.setKernelState('connecting');
                    break;
                case 'busy':
                    this.setKernelState('busy');
                    break;
                case 'idle':
                    this.setKernelState('idle');
                    break;
            }
        }
    }

    handleCellStatus(message) {
        const parentMsgId = message.parent_header?.msg_id;
        if (!parentMsgId) {
            console.warn('Cell status message without parent_header.msg_id:', message);
            return;
        }

        const status = message.content?.status;
        if (!status) {
            console.warn('Cell status message without status:', message);
            return;
        }

        const sequence = message.content?.sequence;

        console.log(`Cell status update: ${parentMsgId.slice(0,8)} -> ${status} (seq: ${sequence})`);

        // Find cell - if not found, cell hasn't been created yet
        const cell = this.cells.get(parentMsgId);
        if (!cell) {
            console.warn(`Cell not found for status update: ${parentMsgId.slice(0,8)}, buffering...`);

            // Buffer status update for when cell arrives
            if (!this.pendingStatuses) {
                this.pendingStatuses = new Map();
            }
            this.pendingStatuses.set(parentMsgId, { status, sequence });
            return;
        }

        // Apply state transition via state machine
        this.setCellState(parentMsgId, status, sequence);
    }

    handleKernelRestarted(message) {
        console.log('Kernel restarted message received:', message);

        // Create a prominent notification cell
        const notificationDiv = document.createElement('div');
        notificationDiv.className = 'cell kernel-restart-notification';

        const notificationContent = document.createElement('div');
        notificationContent.className = 'notification-content';

        const notificationIcon = document.createElement('div');
        notificationIcon.className = 'notification-icon';
        notificationIcon.textContent = '🔄';

        const notificationText = document.createElement('div');
        notificationText.className = 'notification-text';
        notificationText.innerHTML = '<strong>Kernel Restarted</strong><br>All variables and imported modules have been reset.';

        const notificationTimestamp = document.createElement('div');
        notificationTimestamp.className = 'notification-timestamp';
        notificationTimestamp.textContent = new Date().toLocaleTimeString();

        notificationContent.appendChild(notificationIcon);
        notificationContent.appendChild(notificationText);
        notificationContent.appendChild(notificationTimestamp);
        notificationDiv.appendChild(notificationContent);

        // Add to the output area
        this.outputArea.appendChild(notificationDiv);

        // Reset kernel state to idle (clears dead/error states)
        this.setKernelState('idle');

        // Auto-scroll to bottom if enabled
        this.autoscroll();
    }

    handleKernelAutoRestarted(message) {
        console.log('Kernel auto-restarted message received:', message);

        // Create a prominent notification cell with warning/info styling
        const notificationDiv = document.createElement('div');
        notificationDiv.className = 'cell kernel-restart-notification';
        // Add specific auto-restart styling (yellow/warning)
        notificationDiv.style.borderLeftColor = '#ffc107'; // Yellow
        notificationDiv.style.backgroundColor = '#1a1508'; // Dark yellow/amber background

        const notificationContent = document.createElement('div');
        notificationContent.className = 'notification-content';

        const notificationIcon = document.createElement('div');
        notificationIcon.className = 'notification-icon';
        notificationIcon.textContent = '🔄'; // Restart symbol
        notificationIcon.style.color = '#ffc107';

        const notificationText = document.createElement('div');
        notificationText.className = 'notification-text';
        notificationText.innerHTML = '<strong>Kernel Auto-Restarted</strong><br>Kernel died and was automatically restarted.';

        const notificationTimestamp = document.createElement('div');
        notificationTimestamp.className = 'notification-timestamp';
        notificationTimestamp.textContent = new Date().toLocaleTimeString();

        notificationContent.appendChild(notificationIcon);
        notificationContent.appendChild(notificationText);
        notificationContent.appendChild(notificationTimestamp);
        notificationDiv.appendChild(notificationContent);

        // Add to the output area
        this.outputArea.appendChild(notificationDiv);

        // Reset kernel state to idle (clears dead/error states)
        this.setKernelState('idle');

        this.autoscroll();
    }

    handleKernelDied(message) {
        console.log('Kernel died message received:', message);

        // 1. Create Notification Cell
        const notificationDiv = document.createElement('div');
        notificationDiv.className = 'cell kernel-restart-notification';
        // Add specific error styling
        notificationDiv.style.borderLeftColor = '#dc3545'; // Red
        notificationDiv.style.backgroundColor = '#2c0b0e'; // Dark red background

        const content = document.createElement('div');
        content.className = 'notification-content';

        const icon = document.createElement('div');
        icon.className = 'notification-icon';
        icon.textContent = '💀'; // Skull icon
        icon.style.color = '#dc3545';

        const text = document.createElement('div');
        text.className = 'notification-text';
        text.innerHTML = `<strong>Kernel Died</strong><br>${message.content?.reason || 'The process was terminated.'}`;

        const timestamp = document.createElement('div');
        timestamp.className = 'notification-timestamp';
        timestamp.textContent = new Date().toLocaleTimeString();

        content.appendChild(icon);
        content.appendChild(text);
        content.appendChild(timestamp);
        notificationDiv.appendChild(content);

        this.outputArea.appendChild(notificationDiv);

        // 2. Update kernel state to dead (sticky state)
        this.setKernelState('dead');

        this.autoscroll();
    }

    createCell(msgId, code) {
        const cellDiv = document.createElement('div');
        cellDiv.className = 'cell';
        cellDiv.setAttribute('data-msg-id', msgId);
        
        // Create status sidebar
        const sidebarDiv = document.createElement('div');
        sidebarDiv.className = 'cell-sidebar status-queued'; // Start in queued state
        cellDiv.appendChild(sidebarDiv);
        
        // Create input section
        const inputDiv = document.createElement('div');
        inputDiv.className = 'cell-input';
        
        const inputHeader = document.createElement('div');
        inputHeader.className = 'cell-input-header';
        inputHeader.textContent = 'In:';
        
        const codeElement = document.createElement('code');
        codeElement.textContent = code;

        inputDiv.appendChild(inputHeader);
        inputDiv.appendChild(codeElement);

        // New logic for collapsible cells
        const lines = code.split('\n');
        if (lines.length > 4) {
            codeElement.classList.add('collapsed');

            // Create bottom bar
            const bottomBar = document.createElement('div');
            bottomBar.className = 'cell-input-bottom-bar';

            // Create left section with collapse button
            const leftSection = document.createElement('div');
            leftSection.className = 'bottom-bar-left';
            
            const collapseButton = document.createElement('button');
            collapseButton.className = 'collapse-button';
            collapseButton.innerHTML = '▼'; // Down arrow for collapsed state
            leftSection.appendChild(collapseButton);

            // Create center section with status text
            const centerSection = document.createElement('div');
            centerSection.className = 'bottom-bar-center';
            centerSection.textContent = '-collapsed-';

            // Create right section with line count
            const rightSection = document.createElement('div');
            rightSection.className = 'bottom-bar-right';
            
            const lineCount = document.createElement('span');
            lineCount.className = 'line-count';
            lineCount.textContent = `${lines.length} lines`;
            rightSection.appendChild(lineCount);
            
            collapseButton.onclick = () => {
                const isCollapsed = codeElement.classList.toggle('collapsed');
                collapseButton.innerHTML = isCollapsed ? '▼' : '▲'; // Toggle arrow direction
                centerSection.textContent = isCollapsed ? '-collapsed-' : '-expanded-';
            };

            bottomBar.appendChild(leftSection);
            bottomBar.appendChild(centerSection);
            bottomBar.appendChild(rightSection);
            inputDiv.appendChild(bottomBar);
        }
        
        // Create output section
        const outputDiv = document.createElement('div');
        outputDiv.className = 'cell-output';
        
        cellDiv.appendChild(inputDiv);
        cellDiv.appendChild(outputDiv);
        
        return cellDiv;
    }

    renderMimeData(container, data, metadata) {
        const outputDiv = document.createElement('div');
        outputDiv.className = 'output-item';
        
        // Priority order for MIME types
        const mimeOrder = [
            'text/html',
            'text/markdown',
            'image/svg+xml',
            'image/png',
            'image/jpeg',
            'text/latex',
            'application/json',
            'text/plain'
        ];
        
        let rendered = false;
        
        for (const mimeType of mimeOrder) {
            if (data[mimeType] && !rendered) {
                this.renderMimeType(outputDiv, mimeType, data[mimeType], metadata[mimeType]);
                rendered = true;
            }
        }
        
        // Fallback to plain text if nothing was rendered
        if (!rendered && data['text/plain']) {
            this.renderMimeType(outputDiv, 'text/plain', data['text/plain'], {});
        }
        
        if (rendered || data['text/plain']) {
            container.appendChild(outputDiv);
        }
    }

    renderMimeType(container, mimeType, data, metadata) {
        switch (mimeType) {
            case 'text/html':
                const htmlContent = Array.isArray(data) ? data.join('') : data;

                // Check if the HTML contains script tags (e.g., matplotlib animations)
                // Scripts inserted via innerHTML don't execute, so we need an iframe
                if (htmlContent.includes('<script')) {
                    // Use an iframe with srcdoc to create a separate document context
                    // where scripts will execute properly
                    const iframe = document.createElement('iframe');
                    iframe.className = 'output-html-iframe';
                    iframe.style.cssText = 'width: 100%; border: none; background: white; border-radius: 4px;';
                    iframe.sandbox = 'allow-scripts allow-same-origin';

                    // Wrap content in a full HTML document with proper styling
                    const wrappedContent = `
                        <!DOCTYPE html>
                        <html>
                        <head>
                            <style>
                                body {
                                    margin: 0;
                                    padding: 10px;
                                    font-family: sans-serif;
                                    background: white;
                                }
                                /* Style matplotlib animation controls */
                                button { cursor: pointer; }
                            </style>
                        </head>
                        <body>${htmlContent}</body>
                        </html>
                    `;
                    iframe.srcdoc = wrappedContent;

                    // Auto-resize iframe to fit content
                    iframe.onload = () => {
                        try {
                            const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                            const height = iframeDoc.body.scrollHeight;
                            iframe.style.height = (height + 20) + 'px';
                        } catch (e) {
                            // Fallback height if we can't access the content
                            iframe.style.height = '500px';
                        }
                    };

                    container.appendChild(iframe);
                } else {
                    // Simple HTML without scripts - use innerHTML for efficiency
                    const htmlDiv = document.createElement('div');
                    htmlDiv.className = 'output-html';
                    htmlDiv.innerHTML = htmlContent;
                    container.appendChild(htmlDiv);
                }
                break;
                
            case 'text/markdown':
                const mdDiv = document.createElement('div');
                mdDiv.className = 'output-html'; // Reuse same styling as HTML
                mdDiv.innerHTML = marked.parse(Array.isArray(data) ? data.join('') : data);
                container.appendChild(mdDiv);
                break;
                
            case 'image/png':
            case 'image/jpeg':
                const img = document.createElement('img');
                img.className = 'output-image';
                img.src = `data:${mimeType};base64,${data}`;
                img.alt = 'Output image';
                container.appendChild(img);
                break;
                
            case 'image/svg+xml':
                const svgDiv = document.createElement('div');
                svgDiv.innerHTML = Array.isArray(data) ? data.join('') : data;
                container.appendChild(svgDiv);
                break;
                
            case 'text/latex':
                const latexDiv = document.createElement('div');
                latexDiv.className = 'output-latex';
                
                // Get the raw latex string
                let latexString = Array.isArray(data) ? data.join('') : data;
                
                // Strip leading/trailing $ delimiters that IPython includes
                if (latexString.startsWith('$') && latexString.endsWith('$')) {
                    latexString = latexString.substring(1, latexString.length - 1);
                }
                
                try {
                    // Render the cleaned string
                    katex.render(latexString, latexDiv, {
                        throwOnError: false,
                        displayMode: true // Use display mode for centered, larger math
                    });
                    container.appendChild(latexDiv);
                } catch (e) {
                    // Fallback for any other errors
                    const errDiv = document.createElement('pre');
                    errDiv.className = 'output-text output-error'; // Add error class for visibility
                    errDiv.textContent = `KaTeX Error: ${e.message}\n\nOriginal text: ${data}`;
                    container.appendChild(errDiv);
                }
                break;
                
            case 'application/json':
                const jsonDiv = document.createElement('pre');
                jsonDiv.className = 'output-text';
                jsonDiv.textContent = JSON.stringify(data, null, 2);
                container.appendChild(jsonDiv);
                break;
                
            case 'text/plain':
            default:
                const textDiv = document.createElement('pre');
                textDiv.className = 'output-text';
                textDiv.textContent = Array.isArray(data) ? data.join('') : data;
                container.appendChild(textDiv);
                break;
        }
    }


    updateStatus(message, status) {
        // Update the kernel info button to reflect connection status
        this.kernelInfoToggle.className = status;

        // Update the icon based on connection status
        if (status === 'connected') {
            this.kernelInfoToggle.textContent = '⬢'; // Filled hexagon for connected
        } else {
            this.kernelInfoToggle.textContent = '⬡'; // Empty hexagon for disconnected
        }

        // Update the connection status in the dropdown
        const connectionStatusElement = document.getElementById('info-connection-status');
        if (connectionStatusElement) {
            connectionStatusElement.textContent = message;
        }
    }

    setKernelState(state) {
        /**
         * Centralized state management for the kernel status indicator.
         * Updates the icon, CSS classes, and connectionState based on the provided state.
         *
         * @param {string} state - One of: 'disconnected', 'connecting', 'idle', 'busy', 'error', 'dead'
         */

        // Clear any existing error timeout
        if (this.errorTimeout) {
            clearTimeout(this.errorTimeout);
            this.errorTimeout = null;
        }

        // Remove all status-* classes and old connected/disconnected classes from the button
        this.kernelInfoToggle.className = this.kernelInfoToggle.className
            .split(' ')
            .filter(cls => !cls.startsWith('status-') && cls !== 'connected' && cls !== 'disconnected')
            .join(' ');

        // Set the new state
        this.connectionState = state;

        // Apply state-specific styling and icon
        let icon = '⬡'; // Default hollow hexagon
        let statusClass = `status-${state}`;

        switch (state) {
            case 'disconnected':
                icon = '⬡'; // Hollow hexagon
                break;
            case 'connecting':
                icon = '⬢'; // Filled hexagon (will pulse yellow)
                break;
            case 'idle':
                icon = '⬢'; // Filled hexagon (blue)
                break;
            case 'busy':
                icon = '⬢'; // Filled hexagon (green, pulsing)
                break;
            case 'error':
                icon = '!'; // Exclamation mark
                break;
            case 'dead':
                icon = '✕'; // X mark
                break;
        }

        // Update the button
        this.kernelInfoToggle.textContent = icon;
        this.kernelInfoToggle.classList.add(statusClass);

        // Update the connection status in the dropdown
        const connectionStatusElement = document.getElementById('info-connection-status');
        if (connectionStatusElement) {
            const statusMessages = {
                'disconnected': 'Disconnected',
                'connecting': 'Connecting...',
                'idle': 'Idle - Ready',
                'busy': 'Busy - Running',
                'error': 'Error',
                'dead': 'Kernel Died'
            };
            connectionStatusElement.textContent = statusMessages[state] || state;
        }

        console.log(`Kernel state changed to: ${state}`);
    }

    updateAutoscrollButton() {
        if (this.isAutoscrollEnabled) {
            // Hide the button when autoscroll is ON
            this.autoscrollButton.style.display = 'none';
        } else {
            // Show the button when autoscroll is OFF
            this.autoscrollButton.style.display = 'flex';
            this.autoscrollButton.innerHTML = '⌄'; // Downward wedge
            this.autoscrollButton.title = 'Scroll to bottom and enable autoscroll';
        }
    }

    toggleAutoscroll() {
        this.isAutoscrollEnabled = !this.isAutoscrollEnabled;
        this.updateAutoscrollButton();

        // If the user just turned it on, scroll to bottom immediately
        if (this.isAutoscrollEnabled) {
            // Mark this as a programmatic scroll so event handler ignores it
            this.isProgrammaticScroll = true;

            window.scrollTo({
                top: document.documentElement.scrollHeight,
                behavior: 'smooth'
            });

            // Clear flag on next animation frame (after scroll event fires)
            requestAnimationFrame(() => {
                this.isProgrammaticScroll = false;
            });
        }
    }

    autoscroll() {
        // Don't interrupt user if they're actively scrolling
        if (this.isAutoscrollEnabled && !this.isUserScrolling) {
            // Mark this as a programmatic scroll so event handler ignores it
            this.isProgrammaticScroll = true;

            // Scroll to the absolute bottom of the page
            window.scrollTo({
                top: document.documentElement.scrollHeight,
                behavior: 'instant'
            });

            // Clear flag on next animation frame (after scroll event fires)
            requestAnimationFrame(() => {
                this.isProgrammaticScroll = false;
            });
        }
    }

    toggleKernelInfoDropdown() {
        this.kernelInfoDropdown.classList.toggle('hidden');

        // The button is now just an icon, so we don't need to change text
    }

    updateKernelInfoDropdown(kernelId) {
        if (!kernelId || !this.kernelDetails[kernelId]) {
            // Clear the dropdown if no kernel is selected
            document.getElementById('info-kernel-uuid').textContent = '-';
            document.getElementById('info-kernel-name').textContent = '-';
            document.getElementById('info-python-executable').textContent = '-';
            document.getElementById('info-created-at').textContent = '-';
            document.getElementById('info-buffers').textContent = '-';
            return;
        }

        const session = this.kernelDetails[kernelId];
        
        // Update the dropdown content with session information
        document.getElementById('info-kernel-uuid').textContent = session.kernel_id;
        document.getElementById('info-kernel-name').textContent = session.kernel_name || '-';
        document.getElementById('info-python-executable').textContent = session.python_executable || '-';
        
        // Format the creation date
        if (session.created_at) {
            const createdDate = new Date(session.created_at);
            document.getElementById('info-created-at').textContent = createdDate.toLocaleString();
        } else {
            document.getElementById('info-created-at').textContent = '-';
        }
        
        // Format associated buffers
        if (session.associated_buffers && session.associated_buffers.length > 0) {
            document.getElementById('info-buffers').textContent = session.associated_buffers.join(', ');
        } else {
            document.getElementById('info-buffers').textContent = '-';
        }
    }

    showError(message) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'status disconnected';
        errorDiv.textContent = `Error: ${message}`;
        this.outputArea.appendChild(errorDiv);
        
        console.error(message);
    }
}

// Initialize the client when the page loads
document.addEventListener('DOMContentLoaded', () => {
    new QuenchClient();
});

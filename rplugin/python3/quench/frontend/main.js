class QuenchClient {
    constructor() {
        this.ws = null;
        this.kernelId = null;
        this.cells = new Map(); // Map from msg_id to cell element
        this.outputArea = null;
        this.kernelSelect = null;
        this.refreshButton = null;
        this.kernelInfoToggle = null;
        this.kernelInfoDropdown = null;
        this.kernelDetails = {}; // Store detailed kernel information
        this.ansiUp = new AnsiUp(); // ANSI code converter
        this.autoscrollButton = null; // Reference to autoscroll toggle button
        this.isAutoscrollEnabled = true; // Track autoscroll state
        this.activeCellElement = null;     // Tracks the most recently updated cell
        this.isProgrammaticScroll = false; // Differentiates script vs. user scrolls
        
        this.init();
    }

    init() {
        // Get DOM elements
        this.outputArea = document.getElementById('output-area');
        this.kernelSelect = document.getElementById('kernel-select');
        this.refreshButton = document.getElementById('refresh-kernels');
        this.kernelInfoToggle = document.getElementById('kernel-info-toggle');
        this.kernelInfoDropdown = document.getElementById('kernel-info-dropdown');
        this.autoscrollButton = document.getElementById('autoscroll-toggle');
        
        // Set up event handlers
        this.kernelSelect.addEventListener('change', () => this.onKernelSelected());
        this.refreshButton.addEventListener('click', () => this.loadKernels());
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
        
        // Load available kernels
        this.loadKernels();
        
        // Also check URL for kernel_id (backward compatibility)
        const urlKernelId = this.getKernelIdFromUrl();
        if (urlKernelId) {
            setTimeout(() => this.selectKernel(urlKernelId), 500);
        }
    }

    setupScrollHandling() {
        // This event fires only when a user-initiated scroll has finished.
        window.addEventListener('scrollend', () => {
            // If the scroll was initiated by our script, we reset the flag and do nothing.
            if (this.isProgrammaticScroll) {
                this.isProgrammaticScroll = false;
                return;
            }

            // If the scroll was initiated by the user, disable autoscroll.
            if (this.isAutoscrollEnabled) {
                this.isAutoscrollEnabled = false;
                this.updateAutoscrollButton();
            }
        });
    }

    async loadKernels() {
        try {
            this.kernelSelect.innerHTML = '<option value="">Loading kernels...</option>';
            
            const response = await fetch('/api/sessions');
            const data = await response.json();
            
            this.kernelSelect.innerHTML = '<option value="">Select a kernel...</option>';
            
            if (data.sessions && Object.keys(data.sessions).length > 0) {
                // Store detailed kernel information
                this.kernelDetails = data.sessions;
                
                Object.values(data.sessions).forEach(session => {
                    const option = document.createElement('option');
                    option.value = session.kernel_id;
                    option.textContent = `${session.name} (${session.short_id}) - ${session.is_alive ? 'Active' : 'Inactive'}`;
                    this.kernelSelect.appendChild(option);
                });
            } else {
                const option = document.createElement('option');
                option.value = '';
                option.textContent = 'No kernels available - run :QuenchRunCell in Neovim';
                this.kernelSelect.appendChild(option);
            }
        } catch (error) {
            console.error('Failed to load kernels:', error);
            this.kernelSelect.innerHTML = '<option value="">Error loading kernels</option>';
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
            this.updateStatus('Select a kernel to connect...', 'disconnected');
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
            this.updateStatus('No kernel selected', 'disconnected');
            return;
        }

        // Close existing connection
        this.disconnect();

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/${this.kernelId}`;
        
        console.log(`Connecting to WebSocket: ${wsUrl}`);
        this.updateStatus('Connecting...', 'disconnected');
        
        try {
            this.ws = new WebSocket(wsUrl);
            this.setupWebSocketHandlers();
        } catch (error) {
            console.error('Failed to create WebSocket connection:', error);
            this.updateStatus('Failed to connect', 'disconnected');
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
            this.updateStatus('Connected to kernel', 'connected');
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
            this.updateStatus('Connection closed', 'disconnected');
        };

        this.ws.onerror = (event) => {
            console.error('WebSocket error:', event);
            this.updateStatus('Connection error', 'disconnected');
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
                
            case 'quench_cell_status':
                this.handleCellStatus(message);
                break;
                
            default:
                console.log(`Unhandled message type: ${msgType}`);
        }
    }

    handleExecuteInput(message) {
        const msgId = message.header.msg_id;
        const parentMsgId = message.parent_header?.msg_id;
        const code = message.content?.code || '';
        
        console.log(`Execute input: msg_id=${msgId?.slice(0,8)}, parent=${parentMsgId?.slice(0,8)}, code length=${code.length}`);
        
        // The execute_input message's parent_header.msg_id is the original execute request ID
        // This is what all output messages (stream, result, etc.) will reference
        if (parentMsgId) {
            console.log(`Creating cell with ID: ${parentMsgId.slice(0,8)}`);
            const cellElement = this.createCell(parentMsgId, code);
            this.cells.set(parentMsgId, cellElement);
            
            console.log(`Cell created, total cells: ${this.cells.size}`);
            
            // Add to the output area
            this.outputArea.appendChild(cellElement);
            this.activeCellElement = cellElement;
        } else {
            console.warn('Execute input message without parent_header.msg_id:', message);
        }
    }

    handleStream(message) {
        const parentMsgId = message.parent_header?.msg_id;
        if (!parentMsgId) {
            console.warn('Stream message without parent_header.msg_id:', message);
            return;
        }
        
        // Create a cell on-demand if one doesn't exist
        if (!this.cells.has(parentMsgId)) {
            const cellElement = this.createCell(parentMsgId, '# Code executed previously');
            this.cells.set(parentMsgId, cellElement);
            this.outputArea.appendChild(cellElement);
            this.activeCellElement = cellElement;
            
            // Set the sidebar to running state since we're getting output
            const sidebar = cellElement.querySelector('.cell-sidebar');
            if (sidebar) {
                sidebar.className = 'cell-sidebar status-running';
            }
        }
        
        const cell = this.cells.get(parentMsgId);
        const outputDiv = cell.querySelector('.cell-output');
        
        const streamName = message.content?.name || 'stdout';
        const text = message.content?.text || '';
        
        // Create or find existing stream output
        let streamDiv = outputDiv.querySelector(`[data-stream="${streamName}"]`);
        if (!streamDiv) {
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
        }
        
        const textDiv = streamDiv.querySelector('.output-text');
        
        // Handle carriage returns properly
        if (text.includes('\r')) {
            // Convert the incoming text to HTML first
            const convertedText = this.ansiUp.ansi_to_html(text);
            let currentHtml = textDiv.innerHTML;
            
            // Split by \r, but we need to handle this more carefully
            const parts = text.split('\r');
            
            // Process each part
            for (let i = 0; i < parts.length; i++) {
                const part = parts[i];
                
                if (i === 0) {
                    // First part: just append normally
                    currentHtml += this.ansiUp.ansi_to_html(part);
                } else {
                    // Subsequent parts: \r should overwrite the current line
                    // Find the position after the last newline
                    const lastNewlineIndex = currentHtml.lastIndexOf('\n');
                    const lastBrIndex = currentHtml.lastIndexOf('<br>');
                    
                    // Use whichever is more recent
                    const cutIndex = Math.max(lastNewlineIndex, lastBrIndex);
                    
                    if (cutIndex !== -1) {
                        // Cut after the last newline/br and replace with new content
                        if (lastBrIndex > lastNewlineIndex) {
                            currentHtml = currentHtml.substring(0, lastBrIndex + 4) + this.ansiUp.ansi_to_html(part);
                        } else {
                            currentHtml = currentHtml.substring(0, lastNewlineIndex + 1) + this.ansiUp.ansi_to_html(part);
                        }
                    } else {
                        // No previous newlines, this is the first line - replace everything
                        currentHtml = this.ansiUp.ansi_to_html(part);
                    }
                }
            }
            
            textDiv.innerHTML = currentHtml;
        } else {
            // Original behavior: just append the new text
            textDiv.innerHTML += this.ansiUp.ansi_to_html(text);
        }
        
        // Auto-scroll to bottom if enabled
        this.autoscroll();
    }

    handleDisplayData(message) {
        const parentMsgId = message.parent_header?.msg_id;
        if (!parentMsgId) {
            console.warn('Display data message without parent_header.msg_id:', message);
            return;
        }
        
        // Create a cell on-demand if one doesn't exist for this parent message ID
        if (!this.cells.has(parentMsgId)) {
            console.log(`Creating on-demand cell for orphaned display data message: ${parentMsgId.slice(0,8)}`);
            const cellElement = this.createCell(parentMsgId, '# Code executed previously');
            this.cells.set(parentMsgId, cellElement);
            this.outputArea.appendChild(cellElement);
            this.activeCellElement = cellElement;
            
            // Set the sidebar to running state since we're getting output
            const sidebar = cellElement.querySelector('.cell-sidebar');
            if (sidebar) {
                sidebar.className = 'cell-sidebar status-running';
            }
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
        
        // Create a cell on-demand if one doesn't exist for this parent message ID
        if (!this.cells.has(parentMsgId)) {
            console.log(`Creating on-demand cell for orphaned error message: ${parentMsgId.slice(0,8)}`);
            const cellElement = this.createCell(parentMsgId, '# Code executed previously');
            this.cells.set(parentMsgId, cellElement);
            this.outputArea.appendChild(cellElement);
            this.activeCellElement = cellElement;
            
            // Set the sidebar to error state since this is an error message
            const sidebar = cellElement.querySelector('.cell-sidebar');
            if (sidebar) {
                sidebar.className = 'cell-sidebar status-completed-error';
            }
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
        
        // Auto-scroll to bottom if enabled
        this.autoscroll();
    }

    handleStatus(message) {
        const executionState = message.content?.execution_state;
        if (executionState) {
            console.log(`Kernel execution state: ${executionState}`);
            // Could update UI to show kernel busy/idle state
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
        
        console.log(`Cell status update: ${parentMsgId.slice(0,8)} -> ${status}`);
        
        // Find the cell element
        const cell = this.cells.get(parentMsgId);
        if (!cell) {
            console.warn(`Cell not found for status update: ${parentMsgId.slice(0,8)}`);
            return;
        }
        
        // Update the sidebar status
        const sidebar = cell.querySelector('.cell-sidebar');
        if (sidebar) {
            // Remove existing status classes
            sidebar.className = sidebar.className.replace(/status-\w+/g, '');
            // Add new status class
            sidebar.className += ` status-${status.replace('_', '-')}`;
            console.log(`Updated cell ${parentMsgId.slice(0,8)} sidebar to ${status}`);
        } else {
            console.warn(`Sidebar not found in cell ${parentMsgId.slice(0,8)}`);
        }
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
        this.activeCellElement = notificationDiv;
        
        // Auto-scroll to bottom if enabled
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
                const htmlDiv = document.createElement('div');
                htmlDiv.className = 'output-html';
                htmlDiv.innerHTML = Array.isArray(data) ? data.join('') : data;
                container.appendChild(htmlDiv);
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

        // Update the connection status in the dropdown
        const connectionStatusElement = document.getElementById('info-connection-status');
        if (connectionStatusElement) {
            connectionStatusElement.textContent = message;
        }
    }

    updateAutoscrollButton() {
        if (this.isAutoscrollEnabled) {
            this.autoscrollButton.textContent = 'Autoscroll On';
            this.autoscrollButton.className = 'autoscroll-on';
        } else {
            this.autoscrollButton.textContent = 'Autoscroll Off';
            this.autoscrollButton.className = 'autoscroll-off';
        }
    }

    toggleAutoscroll() {
        this.isAutoscrollEnabled = !this.isAutoscrollEnabled;
        this.updateAutoscrollButton();

        // If the user just turned it on, scroll to the latest content.
        if (this.isAutoscrollEnabled) {
            this.autoscroll();
        }
    }

    autoscroll() {
        if (this.isAutoscrollEnabled && this.activeCellElement) {
            // Set a flag to let the scrollend listener know this scroll is programmatic.
            this.isProgrammaticScroll = true;
            this.activeCellElement.scrollIntoView({ behavior: 'smooth', block: 'end' });
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

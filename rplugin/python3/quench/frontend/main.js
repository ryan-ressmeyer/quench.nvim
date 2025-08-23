class QuenchClient {
    constructor() {
        this.ws = null;
        this.kernelId = null;
        this.cells = new Map(); // Map from msg_id to cell element
        this.outputArea = null;
        this.statusElement = null;
        this.kernelIdElement = null;
        this.kernelSelect = null;
        this.refreshButton = null;
        this.ansiUp = new AnsiUp(); // ANSI code converter
        
        this.init();
    }

    init() {
        // Get DOM elements
        this.outputArea = document.getElementById('output-area');
        this.statusElement = document.getElementById('connection-status');
        this.kernelIdElement = document.getElementById('kernel-id');
        this.kernelSelect = document.getElementById('kernel-select');
        this.refreshButton = document.getElementById('refresh-kernels');
        
        // Set up event handlers
        this.kernelSelect.addEventListener('change', () => this.onKernelSelected());
        this.refreshButton.addEventListener('click', () => this.loadKernels());
        
        // Load available kernels
        this.loadKernels();
        
        // Also check URL for kernel_id (backward compatibility)
        const urlKernelId = this.getKernelIdFromUrl();
        if (urlKernelId) {
            setTimeout(() => this.selectKernel(urlKernelId), 500);
        }
    }

    async loadKernels() {
        try {
            this.kernelSelect.innerHTML = '<option value="">Loading kernels...</option>';
            
            const response = await fetch('/api/sessions');
            const data = await response.json();
            
            this.kernelSelect.innerHTML = '<option value="">Select a kernel...</option>';
            
            if (data.sessions && Object.keys(data.sessions).length > 0) {
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
            this.kernelIdElement.textContent = 'None';
            this.updateStatus('Select a kernel to connect...', 'disconnected');
            return;
        }
        
        if (selectedKernelId !== this.kernelId) {
            this.kernelId = selectedKernelId;
            this.kernelIdElement.textContent = selectedKernelId;
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
            
            // Scroll to the new cell
            cellElement.scrollIntoView({ behavior: 'smooth', block: 'start' });
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
        }
        
        const cell = this.cells.get(parentMsgId);
        const outputDiv = cell.querySelector('.cell-output');
        
        const data = message.content?.data || {};
        const metadata = message.content?.metadata || {};
        
        // Render different MIME types
        this.renderMimeData(outputDiv, data, metadata);
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
    }

    handleStatus(message) {
        const executionState = message.content?.execution_state;
        if (executionState) {
            console.log(`Kernel execution state: ${executionState}`);
            // Could update UI to show kernel busy/idle state
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
        
        // Scroll to show the notification
        notificationDiv.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    createCell(msgId, code) {
        const cellDiv = document.createElement('div');
        cellDiv.className = 'cell';
        cellDiv.setAttribute('data-msg-id', msgId);
        
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
        this.statusElement.textContent = message;
        this.statusElement.className = `status ${status}`;
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

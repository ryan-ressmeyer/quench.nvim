class QuenchClient {
    constructor() {
        this.ws = null;
        this.kernelId = null;
        this.cells = new Map(); // Map from msg_id to cell element
        this.outputArea = null;
        this.statusElement = null;
        this.kernelIdElement = null;
        
        this.init();
    }

    init() {
        // Get DOM elements
        this.outputArea = document.getElementById('output-area');
        this.statusElement = document.getElementById('connection-status');
        this.kernelIdElement = document.getElementById('kernel-id');
        
        // Extract kernel ID from URL parameters
        this.kernelId = this.getKernelIdFromUrl();
        
        if (!this.kernelId) {
            this.showError('No kernel_id provided in URL parameters. Expected format: ?kernel_id=xxx');
            return;
        }
        
        // Update UI with kernel ID
        this.kernelIdElement.textContent = this.kernelId;
        
        // Establish WebSocket connection
        this.connect();
    }

    getKernelIdFromUrl() {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get('kernel_id');
    }

    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/${this.kernelId}`;
        
        console.log(`Connecting to WebSocket: ${wsUrl}`);
        
        try {
            this.ws = new WebSocket(wsUrl);
            this.setupWebSocketHandlers();
        } catch (error) {
            console.error('Failed to create WebSocket connection:', error);
            this.updateStatus('Failed to connect', 'disconnected');
        }
    }

    setupWebSocketHandlers() {
        this.ws.onopen = (event) => {
            console.log('WebSocket connection opened');
            this.updateStatus('Connected to kernel', 'connected');
        };

        this.ws.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);
                this.handleMessage(message);
            } catch (error) {
                console.error('Failed to parse WebSocket message:', error, event.data);
            }
        };

        this.ws.onclose = (event) => {
            console.log('WebSocket connection closed:', event.code, event.reason);
            this.updateStatus('Connection closed', 'disconnected');
            
            // Attempt to reconnect after a delay
            setTimeout(() => {
                if (this.ws.readyState === WebSocket.CLOSED) {
                    console.log('Attempting to reconnect...');
                    this.connect();
                }
            }, 3000);
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
        
        console.log(`Received message: ${msgType}`, message);
        
        switch (msgType) {
            case 'execute_input':
                this.handleExecuteInput(message);
                break;
                
            case 'stream':
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
                
            default:
                console.log(`Unhandled message type: ${msgType}`);
        }
    }

    handleExecuteInput(message) {
        const msgId = message.header.msg_id;
        const code = message.content?.code || '';
        
        // Create a new cell for this execution
        const cellElement = this.createCell(msgId, code);
        this.cells.set(msgId, cellElement);
        
        // Add to the output area
        this.outputArea.appendChild(cellElement);
        
        // Scroll to the new cell
        cellElement.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    handleStream(message) {
        const parentMsgId = message.parent_header?.msg_id;
        if (!parentMsgId || !this.cells.has(parentMsgId)) {
            console.warn('Stream message without valid parent cell:', message);
            return;
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
            
            // Add metadata header
            const metadata = document.createElement('div');
            metadata.className = 'output-metadata';
            metadata.textContent = `${streamName}:`;
            streamDiv.appendChild(metadata);
            
            const textDiv = document.createElement('pre');
            textDiv.className = 'output-text';
            streamDiv.appendChild(textDiv);
            
            outputDiv.appendChild(streamDiv);
        }
        
        // Append text to existing stream
        const textDiv = streamDiv.querySelector('.output-text');
        textDiv.textContent += text;
    }

    handleDisplayData(message) {
        const parentMsgId = message.parent_header?.msg_id;
        if (!parentMsgId || !this.cells.has(parentMsgId)) {
            console.warn('Display data message without valid parent cell:', message);
            return;
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
        if (!parentMsgId || !this.cells.has(parentMsgId)) {
            console.warn('Error message without valid parent cell:', message);
            return;
        }
        
        const cell = this.cells.get(parentMsgId);
        const outputDiv = cell.querySelector('.cell-output');
        
        const errorDiv = document.createElement('div');
        errorDiv.className = 'output-item output-error';
        
        const errorName = message.content?.ename || 'Error';
        const errorValue = message.content?.evalue || '';
        const traceback = message.content?.traceback || [];
        
        const errorText = `${errorName}: ${errorValue}\n${traceback.join('\n')}`;
        errorDiv.textContent = errorText;
        
        outputDiv.appendChild(errorDiv);
    }

    handleStatus(message) {
        const executionState = message.content?.execution_state;
        if (executionState) {
            console.log(`Kernel execution state: ${executionState}`);
            // Could update UI to show kernel busy/idle state
        }
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
                // For now, render as text. In a full implementation, you'd use MathJax or KaTeX
                const latexDiv = document.createElement('pre');
                latexDiv.className = 'output-text';
                latexDiv.textContent = Array.isArray(data) ? data.join('') : data;
                container.appendChild(latexDiv);
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
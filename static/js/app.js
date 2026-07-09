document.addEventListener('DOMContentLoaded', function() {
    get_juegos();
    
    // Lógica del 100% automático
    document.getElementById('inputEstado').addEventListener('change', function() {
        const inputPorcentaje = document.getElementById('inputPorcentaje');
        if (this.value === 'Completado') {
            inputPorcentaje.value = 100;
            inputPorcentaje.readOnly = true;
        } else {
            inputPorcentaje.readOnly = false;
        }
    });

    document.getElementById('juegoForm').addEventListener('submit', save_juego);
});

function get_juegos() {
    fetch('/api/juegos')
        .then(response => response.json())
        .then(data => {
            const list = document.querySelector('#gamesList');
            if(!list) return;
            list.innerHTML = '';

            data.forEach(juego => {
                const col = document.createElement('div');
                col.className = 'col';
                col.innerHTML = `
                    <div class="game-card d-flex align-items-center p-3">
                        <div class="game-info flex-grow-1">
                            <div class="d-flex justify-content-between align-items-start">
                                <div>
                                    <h5 class="mb-1">${juego[1]}</h5>
                                    <div class="mb-2"><span class="platform-badge">${juego[2]}</span></div>
                                </div>
                                <div class="text-end">
                                    ${juego[3] === 'Completado' ? '<span class="badge bg-success">Completado</span>' : (juego[3] === 'Jugando' ? '<span class="badge bg-primary">Jugando</span>' : '<span class="badge bg-warning text-dark">sin jugar</span>')}
                                </div>
                            </div>
                            <div class="progress mt-2" style="height: 14px;">
                                <div class="progress-bar ${juego[4] === 100 ? 'bg-success' : 'bg-primary'}" role="progressbar" style="width: ${juego[4]}%;" aria-valuenow="${juego[4]}" aria-valuemin="0" aria-valuemax="100">${juego[4]}%</div>
                            </div>
                        </div>
                        <div class="ms-3 game-actions text-end">
                            <button type="button" class="btn btn-warning btn-sm mb-2" onclick="edit_juego(${juego[0]}, '${juego[1].replace(/'/g, "\\'")}', '${juego[2]}', '${juego[3]}', ${juego[4]})">Editar</button>
                            <button type="button" class="btn btn-danger btn-sm" onclick="delete_juego(${juego[0]})">Eliminar</button>
                        </div>
                    </div>
                `;
                list.appendChild(col);
            });
        });
}

function edit_juego(id, titulo, plataforma, estado, porcentaje) {
    document.getElementById('juegoId').value = id;
    document.getElementById('inputTitulo').value = titulo;
    document.getElementById('inputPlataforma').value = plataforma;
    document.getElementById('inputEstado').value = estado;
    document.getElementById('inputPorcentaje').value = porcentaje;
    
    // Dispara el evento para bloquear el input si es Completado
    document.getElementById('inputEstado').dispatchEvent(new Event('change'));
}

function save_juego(event) {
    event.preventDefault();
    const id = document.getElementById('juegoId').value;
    const data = {
        titulo: document.getElementById('inputTitulo').value,
        plataforma: document.getElementById('inputPlataforma').value,
        estado: document.getElementById('inputEstado').value,
        porcentaje: document.getElementById('inputPorcentaje').value
    };
    
    const url = id ? `/api/juegos/${id}` : '/api/juegos';
    const method = id ? 'PUT' : 'POST';

    fetch(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    }).then(response => { 
        if(response.ok) { 
            document.getElementById('juegoForm').reset(); 
            document.getElementById('juegoId').value = '';
            document.getElementById('inputPorcentaje').readOnly = false;
            get_juegos(); 
        } 
    });
}

function delete_juego(id) {
    if(confirm('¿Eliminar juego?')) {
        fetch(`/api/juegos/${id}`, { method: 'DELETE' }).then(response => { if(response.ok) get_juegos(); });
    }
}

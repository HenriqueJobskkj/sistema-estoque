document.addEventListener("DOMContentLoaded", function () {

    // ---------- Alertas: botão de fechar e sumiço automático ----------
    var alertas = document.querySelectorAll(".alerta");

    alertas.forEach(function (alerta) {

        function fechar() {
            alerta.classList.add("alerta-saindo");       // começa a desaparecer
            setTimeout(function () {
                alerta.remove();                          // remove da página
            }, 300);
        }

        var botaoFechar = alerta.querySelector(".alerta-fechar");
        if (botaoFechar) {
            botaoFechar.addEventListener("click", fechar);
        }

        // Mensagens de sucesso somem sozinhas depois de 6 segundos
        if (alerta.classList.contains("alerta-sucesso")) {
            setTimeout(fechar, 6000);
        }
    });

    // ---------- Confirmação antes de excluir um produto ----------
    var formulariosExcluir = document.querySelectorAll(".form-excluir");

    formulariosExcluir.forEach(function (formulario) {
        formulario.addEventListener("submit", function (evento) {
            var nome = formulario.dataset.nome;
            var confirmou = confirm('Deseja realmente excluir o produto "' + nome + '"?');

            // Se o usuário clicar em "Cancelar", o formulário não é enviado
            if (!confirmou) {
                evento.preventDefault();
            }
        });
    });

    // ---------- Proteção contra clique duplo nos formulários que gravam dados ----------
    var formularios = document.querySelectorAll("form");

    formularios.forEach(function (formulario) {

        // Só formulários POST, e não os de exclusão (que têm a confirmação acima)
        if (formulario.method !== "post" || formulario.classList.contains("form-excluir")) {
            return;
        }

        formulario.addEventListener("submit", function () {
            var botao = formulario.querySelector("button[type='submit']");
            if (!botao) {
                return;
            }

            // Guarda o texto original e desativa o botão para evitar um segundo envio
            botao.dataset.textoOriginal = botao.textContent;
            botao.disabled = true;
            botao.textContent = "Aguarde...";
        });
    });

    // Se o usuário voltar para a página pelo botão "Voltar" do navegador,
    // os botões voltam ao normal
    window.addEventListener("pageshow", function () {
        var botoes = document.querySelectorAll("button[data-texto-original]");
        botoes.forEach(function (botao) {
            botao.disabled = false;
            botao.textContent = botao.dataset.textoOriginal;
        });
    });

    // ---------- Prévia do novo estoque (telas de entrada e de saída) ----------
    var campoProduto = document.getElementById("produto_id");
    var campoQuantidade = document.getElementById("quantidade");
    var previa = document.getElementById("previa");

    function atualizarPrevia() {
        var opcao = campoProduto.options[campoProduto.selectedIndex];
        var quantidade = parseInt(campoQuantidade.value, 10);

        // Sem produto ou sem quantidade válida, não mostra nada
        if (!opcao || !opcao.value || isNaN(quantidade) || quantidade <= 0) {
            previa.textContent = "";
            return;
        }

        var atual = parseInt(opcao.dataset.estoque, 10);

        // O atributo data-tipo do HTML diz se a página é de saída.
        // Na página de entrada ele não existe, e o padrão é entrada.
        var ehSaida = previa.dataset.tipo === "saida";

        if (ehSaida) {
            // Saída maior que o estoque: avisa em vermelho
            if (quantidade > atual) {
                previa.style.color = "#991b1b";
                previa.textContent = "Quantidade insuficiente em estoque. Disponível: " + atual;
                return;
            }

            previa.style.color = "#1e40af";
            previa.textContent = "Estoque atual: " + atual +
                " | Saída: " + quantidade +
                " | Novo estoque: " + (atual - quantidade);
        } else {
            previa.style.color = "#1e40af";
            previa.textContent = "Estoque atual: " + atual +
                " | Entrada: " + quantidade +
                " | Novo estoque: " + (atual + quantidade);
        }
    }

    // Só liga a prévia se estivermos em uma página que tem esses elementos
    if (campoProduto && campoQuantidade && previa) {
        campoProduto.addEventListener("change", atualizarPrevia);
        campoQuantidade.addEventListener("input", atualizarPrevia);
        atualizarPrevia();
    }
});
function confirmCsvUpload() {
    const mode = document.getElementById("upload_mode").value;
    const confirmInput = document.getElementById("confirm_overwrite");
    if (mode !== "overwrite") {
        confirmInput.value = "no";
        return true;
    }

    const accepted = window.confirm(
        "你正在执行覆盖修改，这会删除当前筛选条件下已有卡片并按 CSV 重建，是否继续？"
    );
    confirmInput.value = accepted ? "yes" : "no";
    return accepted;
}

function updateCsvFileName(input) {
    const fileName = document.getElementById("csv-file-name");
    if (!fileName) {
        return;
    }
    fileName.textContent = input.files && input.files.length
        ? input.files[0].name
        : "尚未选择文件";
}

function confirmDeleteBanList(form) {
    const accepted = window.confirm(
        "你将删除当前禁卡表及其卡片记录，此操作不可恢复，是否继续？"
    );
    if (!accepted) {
        return false;
    }

    const confirmation = window.prompt(
        "为防止误触，请输入 DELETE 确认删除：",
        ""
    );
    if (confirmation !== "DELETE") {
        window.alert("未通过删除确认，操作已取消。\n请准确输入 DELETE。");
        return false;
    }

    const hidden = form.querySelector("input[name='confirm_delete']");
    if (!hidden) {
        return false;
    }
    hidden.value = "yes";
    return true;
}

function openCreateBanListModal() {
    const modal = document.getElementById("create-banlist-modal");
    if (modal) {
        modal.classList.add("is-open");
        modal.setAttribute("aria-hidden", "false");
    }
}

function closeCreateBanListModal() {
    const modal = document.getElementById("create-banlist-modal");
    if (modal) {
        modal.classList.remove("is-open");
        modal.setAttribute("aria-hidden", "true");
    }
}

function toggleCreateBanListFile(checkbox) {
    const row = document.getElementById("create-banlist-file-row");
    const fileInput = document.getElementById("create_banlist_csv");
    const useCsvHidden = document.getElementById("create_use_csv");
    const enabled = Boolean(checkbox.checked);

    if (row) {
        row.hidden = !enabled;
    }
    if (fileInput) {
        fileInput.disabled = !enabled;
        fileInput.required = enabled;
        if (!enabled) {
            fileInput.value = "";
        }
    }
    if (useCsvHidden) {
        useCsvHidden.value = enabled ? "yes" : "no";
    }
}

document.addEventListener("DOMContentLoaded", () => {
    const fileInput = document.getElementById("banlist_csv");
    if (fileInput) {
        updateCsvFileName(fileInput);
        fileInput.addEventListener(
            "change",
            () => updateCsvFileName(fileInput)
        );
    }

    const modal = document.getElementById("create-banlist-modal");
    if (modal) {
        modal.addEventListener("click", (event) => {
            if (event.target === modal) {
                closeCreateBanListModal();
            }
        });
    }

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeCreateBanListModal();
        }
    });
});

//
//  CreateAccountView.swift
//  Lyceum-Ledger
//
//  Created by Antoine Nguyen on 10/16/25.
//

import SwiftUI

struct CreateAccountView: View {
    // This view has its own ViewModel instance
    @StateObject private var viewModel = CreateAccountViewModel()
    
    // Use the environment to get a dismiss action
    @Environment(\.dismiss) private var dismiss
    
    var body: some View {
        NavigationView {
            Form {
                Section(header: Text("Account Details")) {
                    TextField("Username", text: $viewModel.username)
                        .autocapitalization(.none)
                    TextField("Email", text: $viewModel.email)
                        .keyboardType(.emailAddress)
                        .autocapitalization(.none)
                }
                
                Section(header: Text("Password")) {
                    SecureField("Password", text: $viewModel.password)
                    SecureField("Confirm Password", text: $viewModel.confirmPassword)
                }
                
                Section {
                    Button("Sign Up") {
                        Task {
                            await viewModel.createAccount()
                            // Optionally dismiss on success
                            // dismiss()
                        }
                    }
                    .disabled(viewModel.isSignUpButtonDisabled)
                }
                
                if viewModel.isLoading {
                    ProgressView()
                }
                
                if let errorMessage = viewModel.errorMessage {
                    Text(errorMessage)
                        .foregroundColor(.red)
                }
            }
            .navigationTitle("Create Account")
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") {
                        dismiss() // This closes the sheet
                    }
                }
            }
        }
    }
}

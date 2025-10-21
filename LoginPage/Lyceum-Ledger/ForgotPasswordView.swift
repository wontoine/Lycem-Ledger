//
//  ForgotPasswordView.swift
//  Lyceum-Ledger
//
//  Created by Antoine Nguyen on 10/21/25.
//

import SwiftUI

struct ForgotPasswordView: View {
    
    @StateObject private var viewModel = ForgotPasswordViewModel()
    
    // This allows us to programmatically dismiss the sheet
    @Environment(\.dismiss) private var dismiss
    
    var body: some View {
        NavigationView {
            Form {
                if viewModel.didSendLink {
                    // Show a success message
                    Section {
                        Text("Success! If an account with that email exists, a reset link has been sent.")
                            .foregroundColor(.green)
                    }
                } else {
                    // Show the email entry form
                    Section(header: Text("Reset Your Password"),
                            footer: Text("Enter the email address you used to sign up.")) {
                        
                        TextField("Email Address", text: $viewModel.email)
                            .keyboardType(.emailAddress)
                            .autocapitalization(.none)
                            .autocorrectionDisabled(true)
                    }
                    
                    Section {
                        Button("Send Reset Link") {
                            Task {
                                await viewModel.sendResetLink()
                            }
                        }
                        .disabled(viewModel.isSubmitButtonDisabled)
                    }
                    
                    if viewModel.isLoading {
                        ProgressView()
                    }
                    
                    if let errorMessage = viewModel.errorMessage {
                        Text(errorMessage)
                            .foregroundColor(.red)
                    }
                }
            }
            .navigationTitle("Forgot Password")
            .navigationBarTitleDisplayMode(.inline)
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

// Preview provider for the new view
struct ForgotPasswordView_Previews: PreviewProvider {
    static var previews: some View {
        ForgotPasswordView()
    }
}
